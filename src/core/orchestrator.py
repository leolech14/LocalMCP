"""
Semantic Tool Orchestrator for MCP
Implements intelligent tool discovery, selection, and composition
Based on research findings for handling hundreds of MCP tools efficiently
"""

import asyncio
import hashlib
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from tenacity import retry, stop_after_attempt, wait_exponential

from ..mcp.tool_registry import ToolRegistry, Tool
from .cache_manager import CacheManager
from .circuit_breaker import CircuitBreaker


@dataclass
class ToolScore:
    tool: Tool
    server_score: float
    tool_score: float
    combined_score: float
    context_relevance: float = 0.0


@dataclass
class ExecutionPlan:
    """Represents an optimized execution plan for multiple tools"""
    stages: List[List[Tool]] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    estimated_duration: float = 0.0
    
    def add_parallel_stage(self, tools: List[Tool]):
        """Add tools that can execute in parallel"""
        self.stages.append(tools)
    
    def add_sequential_stages(self, tools: List[Tool]):
        """Add tools that must execute sequentially"""
        for tool in tools:
            self.stages.append([tool])


class SemanticToolOrchestrator:
    """Advanced tool orchestration with semantic search and intelligent routing"""
    
    def __init__(self, 
                 tool_registry: ToolRegistry,
                 cache_manager: CacheManager,
                 embedding_model: str = "all-MiniLM-L6-v2"):
        self.tool_registry = tool_registry
        self.cache = cache_manager
        self.embedding_model = SentenceTransformer(embedding_model)
        self.capability_graph = CapabilityGraph()
        self.execution_history = defaultdict(list)
        
        # Initialize semantic index
        self.semantic_index = None
        self.tool_embeddings = {}
        self.index_to_tool = {}
        
        # Circuit breakers for each MCP server
        self.circuit_breakers = {}
        
    async def initialize(self):
        """Initialize semantic index with discovered tools"""
        tools = await self.tool_registry.get_all_tools()
        await self._build_semantic_index(tools)
        
    async def _build_semantic_index(self, tools: List[Tool]):
        """Build FAISS index for semantic tool search"""
        if not tools:
            return
            
        # Generate embeddings for each tool
        tool_descriptions = []
        for i, tool in enumerate(tools):
            description = f"{tool.server_name} {tool.name} {tool.description}"
            tool_descriptions.append(description)
            self.index_to_tool[i] = tool
            
        # Create embeddings
        embeddings = self.embedding_model.encode(tool_descriptions)
        
        # Build FAISS index
        dimension = embeddings.shape[1]
        self.semantic_index = faiss.IndexFlatL2(dimension)
        self.semantic_index.add(embeddings.astype('float32'))
        
        # Store embeddings for later use
        for i, (tool, embedding) in enumerate(zip(tools, embeddings)):
            self.tool_embeddings[tool.id] = embedding
            
    async def discover_tools(self, 
                           intent: str, 
                           context: Dict[str, Any],
                           top_k: int = 5) -> List[ToolScore]:
        """Discover relevant tools using semantic search and context"""
        
        # Check cache first
        cache_key = self._generate_cache_key(intent, context)
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        # Semantic similarity search
        query_embedding = self.embedding_model.encode([intent])
        distances, indices = self.semantic_index.search(
            query_embedding.astype('float32'), 
            top_k * 4  # Get more candidates for filtering
        )
        
        candidates = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx in self.index_to_tool:
                tool = self.index_to_tool[idx]
                # Calculate semantic similarity score (inverse of distance)
                similarity = 1.0 / (1.0 + distance)
                candidates.append((tool, similarity))
                
        # Filter by context and capabilities
        filtered = await self._filter_by_context(candidates, context)
        
        # Score and rank tools
        scored_tools = await self._score_tools(filtered, intent, context)
        
        # Cache the result
        await self.cache.set(cache_key, scored_tools[:top_k], ttl=300)
        
        return scored_tools[:top_k]
        
    async def _filter_by_context(self, 
                                candidates: List[Tuple[Tool, float]], 
                                context: Dict[str, Any]) -> List[Tuple[Tool, float]]:
        """Filter tools based on context requirements"""
        filtered = []
        
        for tool, score in candidates:
            # Check if tool matches context requirements
            if await self._matches_context(tool, context):
                filtered.append((tool, score))
                
        return filtered
        
    async def _matches_context(self, tool: Tool, context: Dict[str, Any]) -> bool:
        """Check if tool matches the given context"""
        # Check required capabilities
        if 'required_capabilities' in context:
            tool_caps = set(tool.capabilities)
            required_caps = set(context['required_capabilities'])
            if not required_caps.issubset(tool_caps):
                return False
                
        # Check authentication requirements
        if 'auth_required' in context and context['auth_required']:
            if not tool.requires_auth:
                return False
                
        # Check server availability
        server_id = tool.server_id
        if server_id in self.circuit_breakers:
            if not self.circuit_breakers[server_id].is_available():
                return False
                
        return True
        
    async def _score_tools(self, 
                          candidates: List[Tuple[Tool, float]], 
                          intent: str, 
                          context: Dict[str, Any]) -> List[ToolScore]:
        """Score tools based on multiple factors"""
        scored = []
        
        for tool, semantic_score in candidates:
            # Calculate server-level score
            server_score = await self._calculate_server_score(tool)
            
            # Calculate tool-level score
            tool_score = await self._calculate_tool_score(tool, intent)
            
            # Combine scores using the research-backed formula
            combined_score = (server_score * tool_score) * max(server_score, tool_score)
            
            # Add context relevance
            context_score = await self._calculate_context_relevance(tool, context)
            
            scored.append(ToolScore(
                tool=tool,
                server_score=server_score,
                tool_score=tool_score,
                combined_score=combined_score,
                context_relevance=context_score
            ))
            
        # Sort by combined score
        scored.sort(key=lambda x: x.combined_score * (1 + x.context_relevance), 
                   reverse=True)
        
        return scored
        
    async def _calculate_server_score(self, tool: Tool) -> float:
        """Calculate server reliability and performance score"""
        server_id = tool.server_id
        
        # Check historical performance
        if server_id in self.execution_history:
            history = self.execution_history[server_id]
            if history:
                # Calculate success rate and average latency
                successes = sum(1 for h in history if h['success'])
                success_rate = successes / len(history)
                
                avg_latency = sum(h['latency'] for h in history) / len(history)
                latency_score = 1.0 / (1.0 + avg_latency / 1000)  # Normalize to 0-1
                
                return 0.7 * success_rate + 0.3 * latency_score
                
        return 0.8  # Default score for new servers
        
    async def _calculate_tool_score(self, tool: Tool, intent: str) -> float:
        """Calculate tool-specific relevance score"""
        # Use semantic similarity between tool description and intent
        tool_desc = f"{tool.name} {tool.description}"
        
        tool_embedding = self.embedding_model.encode([tool_desc])
        intent_embedding = self.embedding_model.encode([intent])
        
        # Cosine similarity
        similarity = np.dot(tool_embedding[0], intent_embedding[0]) / (
            np.linalg.norm(tool_embedding[0]) * np.linalg.norm(intent_embedding[0])
        )
        
        return float(similarity)
        
    async def _calculate_context_relevance(self, 
                                         tool: Tool, 
                                         context: Dict[str, Any]) -> float:
        """Calculate how well the tool fits the current context"""
        relevance = 0.0
        
        # Check if tool was recently used successfully in similar context
        if 'session_id' in context:
            session_history = self.execution_history.get(
                f"session_{context['session_id']}", []
            )
            for entry in session_history:
                if entry['tool_id'] == tool.id and entry['success']:
                    relevance += 0.2
                    
        # Check if tool is part of a known workflow
        if 'workflow_type' in context:
            if tool.id in self.capability_graph.get_workflow_tools(
                context['workflow_type']
            ):
                relevance += 0.3
                
        return min(relevance, 1.0)
        
    def _generate_cache_key(self, intent: str, context: Dict[str, Any]) -> str:
        """Generate cache key for tool discovery results"""
        context_str = json.dumps(context, sort_keys=True)
        combined = f"{intent}:{context_str}"
        return hashlib.md5(combined.encode()).hexdigest()
        
    async def create_execution_plan(self, 
                                  tool_calls: List[Dict[str, Any]]) -> ExecutionPlan:
        """Create optimized execution plan for multiple tool calls"""
        plan = ExecutionPlan()
        
        # Analyze dependencies
        dep_graph = await self._analyze_dependencies(tool_calls)
        
        # Find independent groups that can run in parallel
        parallel_groups = self._find_parallel_groups(dep_graph)
        
        # Check resource constraints
        for group in parallel_groups:
            if await self._can_run_parallel(group):
                plan.add_parallel_stage(group)
            else:
                plan.add_sequential_stages(group)
                
        # Estimate execution time
        plan.estimated_duration = await self._estimate_duration(plan)
        
        return plan
        
    async def _analyze_dependencies(self, 
                                  tool_calls: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Analyze dependencies between tool calls"""
        dependencies = {}
        
        for i, call in enumerate(tool_calls):
            call_id = call.get('id', str(i))
            dependencies[call_id] = []
            
            # Check if this call depends on outputs from previous calls
            if 'inputs' in call:
                for input_key, input_value in call['inputs'].items():
                    if isinstance(input_value, str) and input_value.startswith('$'):
                        # Reference to another tool's output
                        dep_id = input_value[1:].split('.')[0]
                        dependencies[call_id].append(dep_id)
                        
        return dependencies
        
    def _find_parallel_groups(self, 
                            dependencies: Dict[str, List[str]]) -> List[List[str]]:
        """Find groups of tools that can execute in parallel"""
        # Topological sort to find execution order
        visited = set()
        groups = []
        
        def can_add_to_group(tool_id: str, group: List[str]) -> bool:
            """Check if tool can be added to current parallel group"""
            # Tool can be added if it doesn't depend on any tool in the group
            # and no tool in the group depends on it
            for other_id in group:
                if other_id in dependencies.get(tool_id, []):
                    return False
                if tool_id in dependencies.get(other_id, []):
                    return False
            return True
            
        for tool_id in dependencies:
            if tool_id not in visited:
                # Try to add to existing group
                added = False
                for group in groups:
                    if can_add_to_group(tool_id, group):
                        group.append(tool_id)
                        visited.add(tool_id)
                        added = True
                        break
                        
                # Create new group if needed
                if not added:
                    groups.append([tool_id])
                    visited.add(tool_id)
                    
        return groups
        
    async def _can_run_parallel(self, tools: List[str]) -> bool:
        """Check if tools can run in parallel based on resource constraints"""
        # Simple heuristic: limit parallel execution based on tool count
        # In production, this would check actual resource usage
        return len(tools) <= 5
        
    async def _estimate_duration(self, plan: ExecutionPlan) -> float:
        """Estimate total execution duration for the plan"""
        total_duration = 0.0
        
        for stage in plan.stages:
            # For parallel execution, duration is the max of all tools
            # For sequential, it's the sum
            stage_duration = 0.0
            
            if len(stage) == 1:
                # Sequential
                tool = stage[0]
                stage_duration = await self._get_tool_avg_duration(tool.id)
            else:
                # Parallel - take the maximum
                durations = []
                for tool in stage:
                    durations.append(await self._get_tool_avg_duration(tool.id))
                stage_duration = max(durations) if durations else 0.0
                
            total_duration += stage_duration
            
        return total_duration
        
    async def _get_tool_avg_duration(self, tool_id: str) -> float:
        """Get average execution duration for a tool"""
        history = self.execution_history.get(tool_id, [])
        if history:
            return sum(h['latency'] for h in history) / len(history)
        return 100.0  # Default 100ms


class CapabilityGraph:
    """Graph-based representation of tool capabilities and relationships"""
    
    def __init__(self):
        self.graph = defaultdict(set)
        self.workflows = defaultdict(list)
        
    def add_capability_relation(self, tool1_id: str, tool2_id: str, relation_type: str):
        """Add a relationship between two tools"""
        self.graph[tool1_id].add((tool2_id, relation_type))
        
    def get_related_tools(self, tool_id: str, relation_type: Optional[str] = None) -> List[str]:
        """Get tools related to the given tool"""
        related = []
        for other_id, rel_type in self.graph.get(tool_id, []):
            if relation_type is None or rel_type == relation_type:
                related.append(other_id)
        return related
        
    def add_workflow(self, workflow_type: str, tool_ids: List[str]):
        """Define a workflow as a sequence of tools"""
        self.workflows[workflow_type] = tool_ids
        
    def get_workflow_tools(self, workflow_type: str) -> List[str]:
        """Get tools that are part of a workflow"""
        return self.workflows.get(workflow_type, [])