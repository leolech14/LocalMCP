#!/bin/bash

# Get local IP address
IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1)

if [ -z "$IP" ]; then
    echo "Could not determine local IP address"
    echo "Using localhost instead"
    IP="localhost"
fi

PORT=8080

echo "========================================"
echo "LocalMCP Project Viewer"
echo "========================================"
echo ""
echo "Starting web server..."
echo ""
echo "To view on your iPhone:"
echo "1. Make sure your iPhone is on the same WiFi network"
echo "2. Open Safari on your iPhone"
echo "3. Go to: http://$IP:$PORT"
echo ""
echo "Available pages:"
echo "- http://$IP:$PORT/project_proposal.html (Color version)"
echo "- http://$IP:$PORT/project_proposal_accessible.html (B&W accessible)"
echo "- http://$IP:$PORT/modular_integration.html (Integration diagram)"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo ""

# Start Python HTTP server
python3 -m http.server $PORT