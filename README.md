# Kav1 Visitor Management System
<div align="center">
  
![Kav1](https://github.com/user-attachments/assets/6bcebb1b-bc3e-4e3b-b4d5-faece9b61698)<svg width="500" height="500" xmlns="http://www.w3.org/2000/svg">
 <g>
  <rect rx="60" id="svg_11" height="500" width="500" y="0" x="0" stroke-width="0" stroke="#000" fill="#000000"/>
  <rect transform="rotate(45 210 325)" stroke-width="0" id="svg_13" height="50" width="200" y="300" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(-45 210 175)" stroke-width="0" id="svg_15" height="50" width="200" y="150" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 100 250)" stroke-width="0" id="svg_19" height="50" width="300" y="225" x="-50" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 400 250)" stroke-width="0" id="svg_20" height="50" width="300" y="225" x="250" stroke="#000" fill="#fff"/>
 </g>

</svg>

</div>


Kav1 is a modern visitor management system designed to streamline guest check-ins and improve security in controlled environments.
It features a PySide6 desktop frontend and a FastAPI backend, connected through a lightweight REST API with support for real-time updates via WebSocket.

Kav1 is ideal for environments where offline-capable, locally hosted visitor management is preferred over cloud-based tools.

## What Kav1 Does

Kav1 provides a complete solution for tracking and managing visitors in offices, buildings, events, or any controlled environment. The system helps organizations maintain security, compliance, and visitor experience through digital visitor management.

### Core Features

#### 🏃‍♂️ **Visitor Registration & Tracking**
- **Register Visitors**: Create visitor profiles with names, unique IDs, and custom properties
- **Entry/Exit Management**: Track when visitors enter and leave the premises with timestamp logging
- **Real-time Status**: View live status of who is currently inside the building
- **Custom Properties**: Store additional visitor information (company, contact details, purpose of visit, etc.)

#### 🔍 **Search & Discovery**
- **Name Search**: Quickly find visitors by name with partial matching
- **ID Lookup**: Search by visitor ID or badge number
- **Property-based Search**: Filter visitors by custom properties (e.g., all visitors from "ABC Company")
- **Advanced Filtering**: Search by key-value pairs in visitor metadata

#### 📊 **Audit & Compliance**
- **Complete Audit Trail**: Every visitor action is logged with timestamps
- **Entry/Exit History**: Track all building access events
- **Visitor Lifecycle**: Log visitor creation, updates, and deletion
- **Compliance Reports**: Export logs for security and compliance purposes

#### 🔄 **Real-time Synchronization**
- **Live Updates**: Multiple client instances sync automatically via WebSocket
- **Instant Notifications**: Status changes appear immediately across all connected clients
- **Multi-user Support**: Multiple staff members can use the system simultaneously

#### 🖥️ **Desktop-First Design**
- **Native Performance**: Built with PySide6 (Qt) for responsive desktop experience
- **Offline Capable**: Works without internet connection using local SQLite database
- **Windows Integration**: Professional installer with desktop shortcuts and system integration

### Use Cases

#### **Office Buildings**
- Track employees, contractors, and visitors
- Manage meeting room access and guest check-ins
- Maintain security logs for building access

#### **Corporate Events**
- Register attendees and speakers
- Track event check-ins and check-outs
- Monitor capacity and attendance in real-time

#### **Healthcare Facilities**
- Manage patient visitors and family members
- Track visitor hours and access restrictions
- Maintain HIPAA-compliant visitor logs

#### **Educational Institutions**
- Register parents, vendors, and guest speakers
- Track campus visitors for security
- Manage event attendance and access control

#### **Manufacturing & Industrial**
- Track contractor and vendor access
- Manage safety training requirements via custom properties
- Monitor facility access for compliance

### Technical Architecture

- **Frontend**: PySide6 desktop application with modern Qt interface
- **Backend**: FastAPI REST API server with automatic OpenAPI documentation
- **Database**: SQLite with SQLAlchemy ORM for reliable local storage
- **Communication**: HTTP REST API + WebSockets for real-time updates
- **Deployment**: Self-contained Windows installer with all dependencies included
- **CI/CD**: Automated builds and releases via GitHub Actions

## Getting Started

### Quick Installation (Windows)

1. **Download**: Get the latest installer from the [Releases page](https://github.com/YonLiud/kav1/releases)
2. **Install**: Run `kav1_setup_*.exe` and follow the installation wizard
3. **Launch**: Use the desktop shortcuts to start both the server and client applications

### Manual Setup (Development)

#### Prerequisites
- Python 3.11 or higher
- Git

#### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/YonLiud/kav1.git
   cd kav1
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the backend server**
   ```bash
   cd backend
   python server.py
   ```
   The API server will be available at `http://localhost:8000`

4. **Start the frontend client** (in a new terminal)
   ```bash
   cd frontend
   python main.py
   ```

### First Time Setup

1. **Launch the Server**: Start the Kav1 Server application - this hosts the API and database
2. **Connect the Client**: Launch the Kav1 App and configure the connection to your server (default: localhost:8000)
3. **Test Connection**: Use the connection dialog to verify client-server communication
4. **Start Managing Visitors**: Begin registering visitors and tracking their entry/exit status

## How to Use Kav1

### Basic Workflow

1. **Register a Visitor**
   - Click "Add Visitor" in the main interface
   - Enter visitor name and unique ID
   - Add custom properties as needed (company, phone, purpose, etc.)

2. **Track Entry/Exit**
   - Select a visitor from the list
   - Click "Check In" when they arrive
   - Click "Check Out" when they leave
   - All actions are automatically logged with timestamps

3. **Monitor Current Status**
   - View all visitors currently inside the building
   - See the latest action (entry time) for each visitor
   - Real-time updates across all connected clients

4. **Search and Find**
   - Use the search feature to find specific visitors
   - Search by name, ID, or custom properties
   - Filter results based on your needs

5. **Review History**
   - Access complete logs of all visitor activities
   - View entry/exit history for specific visitors
   - Export logs for compliance or reporting

### Advanced Features

- **Custom Properties**: Store additional visitor data like company, contact info, access level, etc.
- **Bulk Operations**: Manage multiple visitors efficiently
- **Real-time Sync**: Multiple staff members can use different client instances simultaneously
- **Offline Operation**: Continue working even without internet connectivity

## API Documentation

The Kav1 backend provides a RESTful API for all visitor management operations. When the server is running, you can access:

- **Interactive API Docs**: http://localhost:8000/docs (Swagger UI)
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Key API Endpoints

#### Visitor Management
- `GET /visitors` - List all visitors
- `GET /visitors/inside` - Get visitors currently inside
- `POST /visitor` - Create a new visitor
- `GET /visitors/{visitor_id}` - Get visitor details
- `PUT /visitors/{visitor_id}` - Update visitor information
- `POST /visitors/{visitor_id}/status` - Update entry/exit status
- `POST /visitors/{visitor_id}/delete` - Delete a visitor

#### Search & Discovery
- `GET /visitors/search?search_query=name` - Search visitors by name
- `GET /visitors/search-by-key-value?key=company&value=ABC` - Search by custom properties

#### Logs & Audit
- `GET /logs` - Get recent activity logs
- `GET /logs/{visitor_id}` - Get logs for specific visitor

#### Real-time Updates
- `WebSocket /ws` - Real-time updates and synchronization

## Project Structure

```
kav1/
├── backend/                 # FastAPI server
│   ├── app/
│   │   ├── main.py         # FastAPI application entry point
│   │   ├── models.py       # SQLAlchemy database models
│   │   ├── schemas.py      # Pydantic request/response models
│   │   ├── crud.py         # Database operations
│   │   ├── routes.py       # API endpoints
│   │   ├── database.py     # Database configuration
│   │   ├── websocket.py    # WebSocket handling
│   │   └── visitor_logger.py # Audit logging
│   ├── alembic/            # Database migrations
│   └── server.py           # Server startup script
├── frontend/               # PySide6 desktop client
│   ├── app/
│   │   ├── views/          # UI components and dialogs
│   │   ├── core/           # API client and settings
│   │   └── utils/          # Utilities and logging
│   └── main.py             # Application entry point
├── .github/workflows/      # CI/CD pipeline
├── requirements.txt        # Python dependencies
└── kav1.iss               # Windows installer configuration
```

## Development

### Running Tests
Currently, the project focuses on functional testing through the UI. To test your changes:

1. Start the backend server
2. Launch the frontend client
3. Test visitor registration, status updates, and synchronization
4. Verify WebSocket connectivity and real-time updates

### Building for Production

#### Windows Installer
```bash
# Build both frontend and backend executables
python -m PyInstaller frontend/main.spec
python -m PyInstaller backend/server.spec

# Create installer (requires Inno Setup)
iscc kav1.iss
```

#### Development Build
```bash
# Use the provided build script
build_windows.bat
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with both server and client
5. Submit a pull request

The CI/CD pipeline will automatically:
- Run code formatting checks (Black)
- Build Windows executables
- Create releases for main and dev branches

- Create releases for main and dev branches

## System Requirements

### Server Requirements
- **OS**: Windows 10/11, Linux, or macOS
- **RAM**: 512MB minimum, 1GB recommended
- **Storage**: 100MB for application, additional space for visitor database
- **Network**: Optional - for multi-client setups

### Client Requirements
- **OS**: Windows 10/11 (primary), Linux/macOS (via Python)
- **RAM**: 256MB minimum, 512MB recommended
- **Display**: 1024x768 minimum resolution
- **Network**: Required for connecting to Kav1 server

## Security Considerations

- **Local Data**: All visitor data is stored locally in SQLite database
- **Network**: API communications are unencrypted HTTP (suitable for local networks)
- **Access Control**: No built-in authentication - suitable for trusted environments
- **Data Privacy**: No data is sent to external services or cloud platforms

For enhanced security in production environments, consider:
- Running behind a reverse proxy with HTTPS
- Implementing network-level access controls
- Regular database backups
- Restricting server access to authorized personnel

## Troubleshooting

### Common Issues

**Server won't start**
- Check if port 8000 is already in use
- Verify Python dependencies are installed
- Check for database permission issues

**Client can't connect**
- Verify server is running and accessible
- Check firewall settings on server machine
- Ensure correct server address in client settings

**Real-time updates not working**
- Verify WebSocket connection in client
- Check for network connectivity issues
- Restart both server and client applications

**Database errors**
- Check SQLite database file permissions
- Run Alembic migrations: `alembic upgrade head`
- Backup and recreate database if corrupted

### Getting Help

- **Issues**: Report bugs on [GitHub Issues](https://github.com/YonLiud/kav1/issues)
- **Documentation**: Check the README files in `backend/` and `frontend/` directories
- **API Reference**: Visit http://localhost:8000/docs when server is running

## License

This project is licensed under the [GNU General Public License (GPL) v3.0](https://www.gnu.org/licenses/gpl-3.0.html). 

### What this means:
- ✅ **Use**: Free to use for any purpose
- ✅ **Modify**: Free to modify and customize
- ✅ **Distribute**: Free to distribute original or modified versions
- ✅ **Commercial Use**: Can be used in commercial environments
- ⚠️ **Share-Alike**: Modified versions must also be licensed under GPL
- ⚠️ **Source Code**: Must provide source code when distributing

## Credits

Developed by [Yon Liud](https://github.com/YonLiud) - A modern, offline-capable visitor management solution built with Python, FastAPI, and PySide6.
