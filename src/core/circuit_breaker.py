"""
Circuit Breaker Implementation for MCP Servers
Implements the Elastic Circuit De-Constructor (ECD) pattern for graceful degradation
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Dict
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered
    DECONSTRUCTED = "deconstructed"  # Graceful degradation state


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5
    timeout: float = 30.0  # seconds
    half_open_limit: int = 3
    success_threshold: int = 2
    deconstruction_threshold: int = 10
    reset_timeout: float = 60.0
    

@dataclass
class ServerErrorInfo:
    """Information about server errors"""
    error_type: str
    message: str
    timestamp: float
    retryable: bool
    

class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    def __init__(self, server_id: str, message: str = None):
        self.server_id = server_id
        super().__init__(message or f"Circuit breaker is OPEN for server {server_id}")
        

class ServiceDegradedError(Exception):
    """Raised when service is in degraded state"""
    def __init__(self, server_id: str, fallback_available: bool = False):
        self.server_id = server_id
        self.fallback_available = fallback_available
        super().__init__(f"Service {server_id} is degraded")


class MCPCircuitBreaker:
    """
    Advanced circuit breaker implementation for MCP servers
    Implements the Elastic Circuit De-Constructor pattern
    """
    
    def __init__(self, 
                 server_id: str,
                 config: Optional[CircuitBreakerConfig] = None):
        self.server_id = server_id
        self.config = config or CircuitBreakerConfig()
        
        # State management
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.consecutive_successes = 0
        
        # Timing
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
        self.state_changed_time: float = time.time()
        self.half_open_start_time: Optional[float] = None
        
        # Error tracking
        self.error_history: list[ServerErrorInfo] = []
        self.half_open_attempts = 0
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        
    def is_available(self) -> bool:
        """Check if the circuit breaker allows calls"""
        return self.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN, 
                             CircuitState.DECONSTRUCTED]
        
    async def call(self, 
                   func: Callable,
                   *args,
                   fallback: Optional[Callable] = None,
                   **kwargs) -> Any:
        """
        Execute a function through the circuit breaker
        
        Args:
            func: The function to execute
            fallback: Optional fallback function for degraded state
            *args, **kwargs: Arguments for the function
            
        Returns:
            Result from the function or fallback
            
        Raises:
            CircuitOpenError: If circuit is open and no fallback available
            ServiceDegradedError: If service is degraded with no fallback
        """
        self.total_calls += 1
        
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info(f"Circuit breaker {self.server_id} attempting reset")
                self._transition_to_half_open()
            else:
                if fallback:
                    logger.warning(f"Circuit open for {self.server_id}, using fallback")
                    return await self._execute_fallback(fallback, *args, **kwargs)
                raise CircuitOpenError(self.server_id)
                
        elif self.state == CircuitState.DECONSTRUCTED:
            if fallback:
                logger.info(f"Service {self.server_id} degraded, using fallback")
                return await self._execute_fallback(fallback, *args, **kwargs)
            raise ServiceDegradedError(self.server_id, fallback_available=False)
            
        # Execute the call
        try:
            result = await self._execute_with_timeout(func, *args, **kwargs)
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure(e)
            raise
            
    async def _execute_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with timeout"""
        try:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Call to {self.server_id} timed out")
            
    async def _execute_fallback(self, fallback: Callable, *args, **kwargs) -> Any:
        """Execute fallback function"""
        try:
            return await fallback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Fallback for {self.server_id} also failed: {e}")
            raise
            
    async def _on_success(self):
        """Handle successful call"""
        self.total_successes += 1
        self.last_success_time = time.time()
        self.consecutive_successes += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.config.success_threshold:
                logger.info(f"Circuit breaker {self.server_id} recovered")
                self._transition_to_closed()
                
        elif self.state == CircuitState.DECONSTRUCTED:
            # Check if service is recovering
            if self.consecutive_successes >= self.config.success_threshold * 2:
                logger.info(f"Service {self.server_id} recovering from degraded state")
                self._transition_to_half_open()
                
        # Reset failure count on success in closed state
        if self.state == CircuitState.CLOSED:
            self.failure_count = 0
            
    async def _on_failure(self, error: Exception):
        """Handle failed call"""
        self.total_failures += 1
        self.failure_count += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()
        
        # Record error info
        error_info = ServerErrorInfo(
            error_type=type(error).__name__,
            message=str(error),
            timestamp=time.time(),
            retryable=self._is_retryable_error(error)
        )
        self.error_history.append(error_info)
        
        # Keep only recent errors
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-100:]
            
        # State transitions based on failure count
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                logger.warning(f"Circuit breaker {self.server_id} opening")
                self._transition_to_open()
                
        elif self.state == CircuitState.HALF_OPEN:
            # Immediate transition back to open on failure
            logger.warning(f"Circuit breaker {self.server_id} reopening")
            self._transition_to_open()
            
        elif self.state == CircuitState.OPEN:
            # Check if we should move to deconstructed state
            if self.failure_count >= self.config.deconstruction_threshold:
                logger.error(f"Service {self.server_id} entering degraded state")
                self._transition_to_deconstructed()
                
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit"""
        if self.last_failure_time is None:
            return True
            
        time_since_failure = time.time() - self.last_failure_time
        
        # Exponential backoff for reset attempts
        backoff_time = self.config.reset_timeout * (2 ** min(self.half_open_attempts, 5))
        
        return time_since_failure >= backoff_time
        
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable"""
        # Non-retryable errors
        non_retryable = [
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            NotImplementedError
        ]
        
        return not any(isinstance(error, err_type) for err_type in non_retryable)
        
    def _transition_to_closed(self):
        """Transition to closed state"""
        self.state = CircuitState.CLOSED
        self.state_changed_time = time.time()
        self.failure_count = 0
        self.success_count = 0
        self.half_open_attempts = 0
        self.consecutive_successes = 0
        
    def _transition_to_open(self):
        """Transition to open state"""
        self.state = CircuitState.OPEN
        self.state_changed_time = time.time()
        self.success_count = 0
        
    def _transition_to_half_open(self):
        """Transition to half-open state"""
        self.state = CircuitState.HALF_OPEN
        self.state_changed_time = time.time()
        self.half_open_start_time = time.time()
        self.half_open_attempts += 1
        self.success_count = 0
        self.failure_count = 0
        
    def _transition_to_deconstructed(self):
        """Transition to deconstructed (degraded) state"""
        self.state = CircuitState.DECONSTRUCTED
        self.state_changed_time = time.time()
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics"""
        success_rate = 0.0
        if self.total_calls > 0:
            success_rate = self.total_successes / self.total_calls
            
        return {
            "server_id": self.server_id,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": success_rate,
            "failure_count": self.failure_count,
            "consecutive_successes": self.consecutive_successes,
            "time_in_state": time.time() - self.state_changed_time,
            "recent_errors": len(self.error_history)
        }
        
    def reset(self):
        """Manually reset the circuit breaker"""
        logger.info(f"Manually resetting circuit breaker for {self.server_id}")
        self._transition_to_closed()


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers"""
    
    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self.breakers: Dict[str, MCPCircuitBreaker] = {}
        self.default_config = default_config or CircuitBreakerConfig()
        
    def get_breaker(self, server_id: str) -> MCPCircuitBreaker:
        """Get or create a circuit breaker for a server"""
        if server_id not in self.breakers:
            self.breakers[server_id] = MCPCircuitBreaker(
                server_id, 
                self.default_config
            )
        return self.breakers[server_id]
        
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all circuit breakers"""
        return {
            server_id: breaker.get_metrics()
            for server_id, breaker in self.breakers.items()
        }
        
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self.breakers.values():
            breaker.reset()