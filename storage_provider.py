"""
Base classes and implementations for storage providers
Supports local filesystem, Dropbox, and Google Photos
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional
import tempfile
import shutil
from tqdm import tqdm
from colorama import Fore


class StorageProvider(ABC):
    """Abstract base class for storage providers"""
    
    def __init__(self):
        self.temp_dir = None
        self.photo_metadata = {}  # Map temp paths to cloud metadata
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the storage provider"""
        pass
    
    @abstractmethod
    def list_photos(self, folder: str, date_from: Optional[str], date_to: Optional[str]) -> List[Dict]:
        """List photos from the storage provider"""
        pass
    
    @abstractmethod
    def download_photo(self, photo_metadata: Dict, output_path: Path) -> bool:
        """Download a photo to local filesystem"""
        pass
    
    @abstractmethod
    def delete_photo(self, photo_path: str, cloud_id: str = None) -> bool:
        """Delete a photo from the storage provider (with optional cloud_id for OneDrive)"""
        pass
    
    @abstractmethod
    def get_display_name(self) -> str:
        """Get the display name of this provider"""
        pass
    
    @abstractmethod
    def supports_automated_deletion(self) -> bool:
        """Whether this provider supports automated deletion"""
        pass
    
    def download_photos_for_analysis(self, photos: List[Dict], filter_name: str = "") -> List[Path]:
        """
        Common method to download photos temporarily for analysis
        
        Args:
            photos: List of photo metadata dictionaries
            filter_name: Description of the filter (for display)
        
        Returns:
            List of local paths to downloaded photos
        """
        if not photos:
            print(f"{Fore.YELLOW}No photos found matching criteria")
            return []
        
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix='photocleaner_')
        print(f"{Fore.CYAN}Downloading {len(photos)} photos to temporary directory for analysis...")
        if filter_name:
            print(f"{Fore.CYAN}{filter_name}")
        
        downloaded_images = []
        
        for photo in tqdm(photos, desc="Downloading"):
            # Handle different naming conventions: 'filename' (Google Photos) or 'name' (Dropbox)
            filename = photo.get('filename') or photo.get('name', 'unknown')
            temp_path = Path(self.temp_dir) / filename
            if self.download_photo(photo, temp_path):
                downloaded_images.append(temp_path)
                # Store metadata for later reference
                self.photo_metadata[str(temp_path)] = photo
        
        print(f"{Fore.GREEN}Downloaded {len(downloaded_images)} images from {self.get_display_name()}")
        return downloaded_images
    
    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir:
            try:
                shutil.rmtree(self.temp_dir)
                print(f"{Fore.CYAN}Cleaned up temporary files")
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not clean up temp directory: {e}")
    
    def get_cloud_path(self, temp_path: Path) -> Optional[str]:
        """Get the cloud path for a temporary local path"""
        metadata = self.photo_metadata.get(str(temp_path))
        if metadata:
            return metadata.get('path') or metadata.get('id')
        return None


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider"""
    
    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
    
    def authenticate(self) -> bool:
        """Local storage doesn't need authentication"""
        if not self.directory.exists():
            print(f"{Fore.RED}Error: Directory does not exist: {self.directory}")
            return False
        return True
    
    def list_photos(self, folder: str = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """Local storage lists photos directly, no download needed"""
        # This method is not used for local storage
        # Photos are found directly in find_images()
        return []
    
    def download_photo(self, photo_metadata: Dict, output_path: Path) -> bool:
        """Local storage doesn't need to download"""
        return True
    
    def delete_photo(self, photo_path: str, cloud_id: str = None) -> bool:
        """Delete a local file"""
        try:
            Path(photo_path).unlink()
            return True
        except Exception as e:
            print(f"{Fore.RED}Error deleting {photo_path}: {e}")
            return False
    
    def get_display_name(self) -> str:
        return "Local Filesystem"
    
    def supports_automated_deletion(self) -> bool:
        return True
    
    def get_cloud_path(self, temp_path: Path) -> Optional[str]:
        """For local storage, return the path itself"""
        return str(temp_path)


class DropboxStorageProvider(StorageProvider):
    """Dropbox cloud storage provider"""
    
    def __init__(self, dropbox_client, folder: str = '', use_search_api: bool = False):
        super().__init__()
        self.client = dropbox_client
        self.folder = folder
        self.use_search_api = use_search_api
    
    def authenticate(self) -> bool:
        """Dropbox authentication is handled during client creation"""
        return self.client is not None
    
    def list_photos(self, folder: str = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """List photos from Dropbox"""
        folder = folder or self.folder
        return self.client.list_photos(
            folder,
            date_from=date_from,
            date_to=date_to,
            use_search_api=self.use_search_api
        )
    
    def download_photo(self, photo_metadata: Dict, output_path: Path) -> bool:
        """Download a photo from Dropbox"""
        return self.client.download_photo(photo_metadata['path'], output_path)
    
    def delete_photo(self, photo_path: str, cloud_id: str = None) -> bool:
        """Move photo to Dropbox trash folder"""
        return self.client.move_photo_to_trash(photo_path)
    
    def get_display_name(self) -> str:
        return f"Dropbox ({self.folder or 'root'})"
    
    def supports_automated_deletion(self) -> bool:
        return True
    
    def get_cloud_path(self, temp_path: Path) -> Optional[str]:
        """Get Dropbox path for a temporary file"""
        metadata = self.photo_metadata.get(str(temp_path))
        return metadata.get('path') if metadata else None


class GooglePhotosStorageProvider(StorageProvider):
    """Google Photos cloud storage provider"""
    
    def __init__(self, google_photos_client, album: str = ''):
        super().__init__()
        self.client = google_photos_client
        self.album = album
    
    def authenticate(self) -> bool:
        """Google Photos authentication is handled during client creation"""
        return self.client is not None
    
    def list_photos(self, folder: str = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """List photos from Google Photos"""
        album = folder or self.album
        return self.client.list_photos(
            album_name=album if album else None,
            date_from=date_from,
            date_to=date_to
        )
    
    def download_photo(self, photo_metadata: Dict, output_path: Path) -> bool:
        """Download a photo from Google Photos"""
        return self.client.download_photo(photo_metadata['url'], output_path)
    
    def delete_photo(self, photo_path: str, cloud_id: str = None) -> bool:
        """Google Photos doesn't support automated deletion"""
        # Just return False to indicate it wasn't deleted
        # The calling code will handle this appropriately
        return False
    
    def get_display_name(self) -> str:
        album_str = f" - Album: {self.album}" if self.album else ""
        return f"Google Photos{album_str}"
    
    def supports_automated_deletion(self) -> bool:
        return False
    
    def get_cloud_path(self, temp_path: Path) -> Optional[str]:
        """Get Google Photos ID for a temporary file"""
        metadata = self.photo_metadata.get(str(temp_path))
        return metadata.get('id') if metadata else None


class OneDriveStorageProvider(StorageProvider):
    """OneDrive cloud storage provider"""
    
    def __init__(self, onedrive_client, folder: str = ''):
        super().__init__()
        self.client = onedrive_client
        self.folder = folder
    
    def authenticate(self) -> bool:
        """OneDrive authentication is handled during client creation"""
        return self.client is not None
    
    def list_photos(self, folder: str = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """List photos from OneDrive"""
        folder = folder or self.folder
        return self.client.list_photos(
            folder,
            date_from=date_from,
            date_to=date_to
        )
    
    def download_photo(self, photo_metadata: Dict, output_path: Path) -> bool:
        """Download a photo from OneDrive"""
        return self.client.download_photo(photo_metadata, output_path)
    
    def delete_photo(self, photo_path: str, cloud_id: str = None) -> bool:
        """Move photo to OneDrive trash folder"""
        # The photo_path from JSON is the OneDrive path (e.g., "/photos/image.jpg")
        # First try using the provided cloud_id (from fast mode JSON)
        if cloud_id:
            return self.client.move_photo_to_trash(cloud_id)
        
        # Otherwise, look up the item ID from our metadata (from normal mode)
        for temp_path, metadata in self.photo_metadata.items():
            stored_path = metadata.get('path')
            if stored_path == photo_path:
                item_id = metadata.get('id')
                if item_id:
                    return self.client.move_photo_to_trash(item_id)
        
        # If not found in metadata, it means we're in fast mode without cloud_id
        # This shouldn't happen if the JSON was generated correctly
        print(f"{Fore.YELLOW}Warning: Cannot delete {photo_path} - item ID not found")
        print(f"{Fore.YELLOW}Make sure the JSON file was generated from OneDrive mode")
        return False
    
    def get_display_name(self) -> str:
        return f"OneDrive ({self.folder or 'root'})"
    
    def supports_automated_deletion(self) -> bool:
        return True
    
    def get_cloud_path(self, temp_path: Path) -> Optional[str]:
        """Get OneDrive path for a temporary file"""
        metadata = self.photo_metadata.get(str(temp_path))
        if metadata:
            # Return the stored OneDrive path
            return metadata.get('path')
        return None

