import os
import sqlite3
import json
import time
from typing import Dict, Any, Optional, List, Tuple
from rich.console import Console

console = Console()

# Database version - increment this when schema changes
DB_VERSION = 1

# Database filename
DB_FILENAME = "vmb_manifest.db"

class ManifestDB:
    """SQLite-based manifest database implementation optimized for large collections."""
    
    def __init__(self, db_path: str):
        """Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self.schema_initialized = False
    
    def connect(self) -> bool:
        """Establish a connection to the database.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Enable WAL mode for better concurrency and performance
            self.conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            
            # Enable foreign keys
            self.conn.execute("PRAGMA foreign_keys=ON")
            
            # Better performance with these settings
            self.conn.execute("PRAGMA temp_store=MEMORY")
            self.conn.execute("PRAGMA cache_size=10000")
            
            # Row factory for easier dictionary access
            self.conn.row_factory = sqlite3.Row
            
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error connecting to database: {e}[/]")
            return False
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def init_schema(self) -> bool:
        """Initialize the database schema if needed.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            if not self.connect():
                return False
        
        try:
            # Check if schema already exists
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='info'")
            if cursor.fetchone():
                # Check version
                cursor.execute("SELECT value FROM info WHERE key='version'")
                version = cursor.fetchone()
                if version and int(version[0]) == DB_VERSION:
                    self.schema_initialized = True
                    return True
                else:
                    # Handle version mismatch/upgrades here if needed
                    console.print(f"[yellow]Warning: Database version mismatch. Expected {DB_VERSION}, found {version[0] if version else 'none'}.[/]")
                    # For now, we'll just recreate the database
                    self.drop_schema()
            
            # Create tables
            with self.conn:
                # Info table for metadata
                self.conn.execute("""
                CREATE TABLE IF NOT EXISTS info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """)
                
                # Set version
                self.conn.execute("INSERT OR REPLACE INTO info (key, value) VALUES (?, ?)", 
                                 ("version", str(DB_VERSION)))
                
                # Videos table
                self.conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    uri TEXT PRIMARY KEY,
                    name TEXT,
                    filename TEXT,
                    quality TEXT,
                    sha256 TEXT,
                    download_time_utc TEXT,
                    api_modified_time TEXT,
                    filesize INTEGER,
                    metadata TEXT  -- Additional JSON metadata
                )
                """)
                
                # Create indices for common queries
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_filename ON videos(filename)")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_download_time ON videos(download_time_utc)")
                
                self.schema_initialized = True
                return True
                
        except sqlite3.Error as e:
            console.print(f"[red]Error initializing database schema: {e}[/]")
            return False
    
    def drop_schema(self) -> bool:
        """Drop all tables (used for schema upgrades).
        
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            if not self.connect():
                return False
        
        try:
            with self.conn:
                self.conn.execute("DROP TABLE IF EXISTS videos")
                self.conn.execute("DROP TABLE IF EXISTS info")
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error dropping schema: {e}[/]")
            return False
    
    def get_video(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get a video entry by URI.
        
        Args:
            uri: Video URI
            
        Returns:
            Dictionary with video data or None if not found
        """
        if not self.conn:
            if not self.connect():
                return None
        
        if not self.schema_initialized:
            if not self.init_schema():
                return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE uri = ?", (uri,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Convert to dictionary
            result = dict(row)
            
            # Parse metadata JSON if present
            if result.get("metadata"):
                try:
                    result["metadata"] = json.loads(result["metadata"])
                except json.JSONDecodeError:
                    result["metadata"] = {}
            
            return result
        except sqlite3.Error as e:
            console.print(f"[red]Error retrieving video {uri}: {e}[/]")
            return None
    
    def update_video(self, video_data: Dict[str, Any]) -> bool:
        """Add or update a video in the database.
        
        Args:
            video_data: Dictionary with video data (must contain 'uri' key)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            if not self.connect():
                return False
        
        if not self.schema_initialized:
            if not self.init_schema():
                return False
        
        uri = video_data.get("uri")
        if not uri:
            console.print("[red]Error: Cannot update video without URI[/]")
            return False
        
        try:
            # Extract known fields
            name = video_data.get("name")
            filename = video_data.get("filename")
            quality = video_data.get("quality")
            sha256 = video_data.get("sha256")
            download_time_utc = video_data.get("download_time_utc")
            api_modified_time = video_data.get("api_modified_time")
            filesize = video_data.get("filesize", 0)
            
            # Store additional fields as JSON metadata
            metadata = {k: v for k, v in video_data.items() 
                       if k not in ("uri", "name", "filename", "quality", "sha256", 
                                   "download_time_utc", "api_modified_time", "filesize")}
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            with self.conn:
                self.conn.execute("""
                INSERT OR REPLACE INTO videos 
                (uri, name, filename, quality, sha256, download_time_utc, api_modified_time, filesize, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (uri, name, filename, quality, sha256, download_time_utc, 
                     api_modified_time, filesize, metadata_json))
            
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error updating video {uri}: {e}[/]")
            return False
    
    def delete_video(self, uri: str) -> bool:
        """Delete a video from the database.
        
        Args:
            uri: Video URI
            
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            if not self.connect():
                return False
        
        if not self.schema_initialized:
            if not self.init_schema():
                return False
        
        try:
            with self.conn:
                self.conn.execute("DELETE FROM videos WHERE uri = ?", (uri,))
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error deleting video {uri}: {e}[/]")
            return False
    
    def get_all_videos(self) -> Dict[str, Dict[str, Any]]:
        """Get all videos from the database.
        
        Returns:
            Dictionary mapping URI to video data
        """
        if not self.conn:
            if not self.connect():
                return {}
        
        if not self.schema_initialized:
            if not self.init_schema():
                return {}
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos")
            rows = cursor.fetchall()
            
            result = {}
            for row in rows:
                data = dict(row)
                uri = data.pop("uri", None)
                if not uri:
                    continue
                
                # Parse metadata JSON if present
                if data.get("metadata"):
                    try:
                        data["metadata"] = json.loads(data["metadata"])
                    except json.JSONDecodeError:
                        data["metadata"] = {}
                
                result[uri] = data
            
            return result
        except sqlite3.Error as e:
            console.print(f"[red]Error retrieving all videos: {e}[/]")
            return {}
    
    def get_videos_by_filenames(self, filenames: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get videos by filenames.
        
        Args:
            filenames: List of filenames to find
            
        Returns:
            Dictionary mapping URI to video data for matching videos
        """
        if not filenames:
            return {}
        
        if not self.conn:
            if not self.connect():
                return {}
        
        if not self.schema_initialized:
            if not self.init_schema():
                return {}
        
        try:
            cursor = self.conn.cursor()
            # SQLite IN clause has limitations, so we'll build a query with parameters
            placeholders = ", ".join(["?"] * len(filenames))
            cursor.execute(f"SELECT * FROM videos WHERE filename IN ({placeholders})", filenames)
            rows = cursor.fetchall()
            
            result = {}
            for row in rows:
                data = dict(row)
                uri = data.pop("uri", None)
                if not uri:
                    continue
                
                # Parse metadata JSON if present
                if data.get("metadata"):
                    try:
                        data["metadata"] = json.loads(data["metadata"])
                    except json.JSONDecodeError:
                        data["metadata"] = {}
                
                result[uri] = data
            
            return result
        except sqlite3.Error as e:
            console.print(f"[red]Error retrieving videos by filenames: {e}[/]")
            return {}
    
    def count_videos(self) -> int:
        """Count the number of videos in the database.
        
        Returns:
            Number of videos, or 0 if error
        """
        if not self.conn:
            if not self.connect():
                return 0
        
        if not self.schema_initialized:
            if not self.init_schema():
                return 0
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.Error as e:
            console.print(f"[red]Error counting videos: {e}[/]")
            return 0
    
    def begin_transaction(self):
        """Start a transaction for batch operations."""
        if not self.conn:
            if not self.connect():
                return
        
        try:
            self.conn.execute("BEGIN TRANSACTION")
        except sqlite3.Error as e:
            console.print(f"[red]Error starting transaction: {e}[/]")
    
    def commit_transaction(self):
        """Commit the current transaction."""
        if not self.conn:
            return
        
        try:
            self.conn.execute("COMMIT")
        except sqlite3.Error as e:
            console.print(f"[red]Error committing transaction: {e}[/]")
    
    def convert_from_json(self, json_path: str) -> bool:
        """Convert a JSON manifest to the SQLite database.
        
        Args:
            json_path: Path to the JSON manifest file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(json_path):
                console.print(f"[yellow]Warning: JSON manifest not found at {json_path}[/]")
                return False
            
            with open(json_path, "r") as f:
                manifest_data = json.load(f)
            
            if not isinstance(manifest_data, dict):
                console.print(f"[red]Error: Invalid JSON manifest structure[/]")
                return False
            
            # Connect and initialize schema
            if not self.conn:
                if not self.connect():
                    return False
            
            if not self.schema_initialized:
                if not self.init_schema():
                    return False
            
            # Begin transaction for efficiency
            self.begin_transaction()
            
            count = 0
            try:
                for uri, entry in manifest_data.items():
                    # Make sure we have a valid URI
                    if not uri or not uri.startswith("/videos/"):
                        console.print(f"[yellow]Warning: Skipping invalid URI: {uri}[/]")
                        continue
                    
                    # Create a copy of the entry and add the URI
                    video_data = entry.copy()
                    video_data["uri"] = uri
                    
                    # Update in database
                    if self.update_video(video_data):
                        count += 1
                
                # Commit all changes
                self.commit_transaction()
                
                console.print(f"[green]Successfully converted {count} entries from JSON to database.[/]")
                return True
            except Exception as e:
                console.print(f"[red]Error during conversion: {e}[/]")
                return False
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing JSON manifest: {e}[/]")
            return False
        except Exception as e:
            console.print(f"[red]Unexpected error during conversion: {e}[/]")
            return False

# Helper functions for compatibility with existing code

def get_db_path(dest_dir: str) -> str:
    """Returns the expected path to the database file in the destination directory."""
    return os.path.join(dest_dir, DB_FILENAME)

def load_manifest_db(dest_dir: str) -> Tuple[ManifestDB, Dict[str, Dict[str, Any]]]:
    """Load the manifest database and return both the DB connection and data.
    
    This provides compatibility with the existing JSON-based code.
    
    Args:
        dest_dir: Destination directory
        
    Returns:
        Tuple of (ManifestDB instance, dictionary representation of manifest)
    """
    db_path = get_db_path(dest_dir)
    json_path = os.path.join(dest_dir, "vmb_manifest.json")
    
    # Initialize the database
    db = ManifestDB(db_path)
    
    # If database doesn't exist but JSON does, convert from JSON
    if not os.path.exists(db_path) and os.path.exists(json_path):
        console.print(f"[yellow]First-time database creation: Converting from JSON manifest...[/]")
        if not db.connect() or not db.init_schema():
            console.print(f"[red]Error initializing database. Falling back to empty manifest.[/]")
            return db, {}
        
        if not db.convert_from_json(json_path):
            console.print(f"[yellow]Warning: Could not convert from JSON. Starting with empty database.[/]")
    
    # Connect and initialize
    if not db.connect() or not db.init_schema():
        console.print(f"[red]Error connecting to database. Using empty manifest.[/]")
        return db, {}
    
    # Load all videos
    manifest_data = db.get_all_videos()
    
    return db, manifest_data

def save_manifest_db(db: ManifestDB, manifest_data: Dict[str, Dict[str, Any]]) -> bool:
    """Save the manifest data to the database.
    
    This provides compatibility with the existing JSON-based code.
    
    Args:
        db: ManifestDB instance
        manifest_data: Dictionary representation of manifest
        
    Returns:
        True if successful, False otherwise
    """
    if not db.conn:
        if not db.connect():
            console.print(f"[red]Error connecting to database for save.[/]")
            return False
    
    if not db.schema_initialized:
        if not db.init_schema():
            console.print(f"[red]Error initializing database schema for save.[/]")
            return False
    
    try:
        # Begin transaction for efficiency
        db.begin_transaction()
        
        for uri, entry in manifest_data.items():
            # Skip entries without URI
            if not uri:
                continue
            
            # Create a copy of the entry and add the URI
            video_data = entry.copy()
            video_data["uri"] = uri
            
            # Update in database
            db.update_video(video_data)
        
        # Commit all changes
        db.commit_transaction()
        
        return True
    except Exception as e:
        console.print(f"[red]Error saving to database: {e}[/]")
        return False

def update_manifest_entry_db(
    db: ManifestDB,
    manifest_data: Dict[str, Dict[str, Any]],
    video_data: Dict[str, Any], 
    filepath: str,
    quality: str,
    sha256_hash: str
) -> bool:
    """Update a single entry in both the in-memory manifest and the database.
    
    Args:
        db: ManifestDB instance
        manifest_data: Dictionary representation of manifest
        video_data: Video metadata
        filepath: Path to the downloaded file
        quality: Video quality
        sha256_hash: SHA256 hash of the file
        
    Returns:
        True if successful, False otherwise
    """
    video_uri = video_data.get("uri")
    if not video_uri:
        console.print(f"[yellow]Warning:[/yellow] Cannot update manifest for video with missing URI: {video_data.get('name')}")
        return False

    filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    
    # Update in-memory manifest
    manifest_data[video_uri] = {
        "filename": os.path.basename(filepath),
        "quality": quality,
        "sha256": sha256_hash,
        "download_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_modified_time": video_data.get("modified_time"),
        "filesize": filesize,
        "name": video_data.get("name") # Store name for easier identification
    }
    
    # Update database directly
    update_data = manifest_data[video_uri].copy()
    update_data["uri"] = video_uri
    
    return db.update_video(update_data) 