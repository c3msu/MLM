#!/bin/bash
# The Dial - Start Script
# Starts the backend API server

cd "$(dirname "$0")"

echo "=========================================="
echo "The Dial - Starting Server"
echo "=========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "backend/venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv backend/venv
fi

echo "📦 Installing dependencies..."
source backend/venv/bin/activate
pip install -q -r backend/requirements.txt

# Initialize database
echo "🗄️  Initializing database..."
cd backend
python3 -c "from data_service import DataService; ds = DataService('macro_data.db', 'data'); ds.init_database(); ds.bootstrap_defaults()"
cd ..

# Start server
echo ""
echo "🚀 Starting server..."
echo "📱 Dashboard: http://localhost:8000/dashboard.html"
echo "📊 API: http://localhost:8000/api/v1/dashboard"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

cd backend
python3 main.py
