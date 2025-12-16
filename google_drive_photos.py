"""
Google Drive API Client for accessing Google Photos
Using Drive API as workaround for deprecated Photos Library API scopes
"""

import json
import os
import pickle
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from colorama import Fore

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False


# Scopes required for Google Drive (to access photos via Google Photos integration)
# drive.photos.readonly: Specifically for photos stored in Google Photos (accessed via Drive)
# drive: Full access needed for deletion capability
SCOPES = ['https://www.googleapis.com/auth/drive.photos.readonly',
          'https://www.googleapis.com/auth/drive']


class GoogleDrivePhotosClient:
    """Client for accessing photos via Google Drive API"""
    
    def __init__(self):
        self.service = None
        self.creds = None
        self.token_path = Path.home() / '.photocleaner_drive_token.pickle'
    
    def authenticate(self, credentials_file: str = 'google_photos_credentials.json') -> bool:
        """
        Authenticate with Google Drive
        
        Args:
            credentials_file: Path to OAuth 2.0 client credentials JSON file
        
        Returns:
            True if authentication successful, False otherwise
        """
        creds_path = Path(credentials_file)
        
        if not creds_path.exists():
            print(f"{Fore.RED}Error: Google credentials file not found: {credentials_file}")
            print(f"{Fore.YELLOW}Use the same credentials file from Google Photos setup")
            return False
        
        # Check if we have cached credentials
        if self.token_path.exists():
            try:
                with open(self.token_path, 'rb') as token:
                    self.creds = pickle.load(token)
                    
                # Verify scopes match - if not, force re-authentication
                if self.creds and hasattr(self.creds, 'scopes'):
                    cached_scopes = set(self.creds.scopes) if self.creds.scopes else set()
                    required_scopes = set(SCOPES)
                    if cached_scopes != required_scopes:
                        print(f"{Fore.YELLOW}Cached credentials have different scopes, re-authenticating...")
                        self.creds = None
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not load cached credentials: {e}")
                self.creds = None
        
        # If no valid credentials, authenticate
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    print(f"{Fore.CYAN}Refreshing Google Drive access token...")
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"{Fore.YELLOW}Could not refresh token: {e}")
                    self.creds = None
            
            if not self.creds:
                try:
                    print(f"{Fore.CYAN}Opening browser for Google Drive authentication...")
                    print(f"{Fore.YELLOW}Note: We're using Google Drive API to access your photos")
                    print(f"{Fore.YELLOW}(Google Photos API scopes were deprecated in March 2025)")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(creds_path), SCOPES)
                    self.creds = flow.run_local_server(port=0)
                except Exception as e:
                    print(f"{Fore.RED}Authentication failed: {e}")
                    return False
            
            # Save credentials for next time
            try:
                with open(self.token_path, 'wb') as token:
                    pickle.dump(self.creds, token)
                print(f"{Fore.GREEN}✓ Credentials cached for future use")
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not cache credentials: {e}")
        
        try:
            self.service = build('drive', 'v3', credentials=self.creds)
            print(f"{Fore.GREEN}✓ Successfully connected to Google Drive")
            return True
        except Exception as e:
            print(f"{Fore.RED}Failed to build Google Drive service: {e}")
            return False
    
    def list_photos(self, album_name: Optional[str] = None, 
                    date_from: Optional[str] = None, 
                    date_to: Optional[str] = None) -> List[Dict]:
        """
        List photos from Google Drive (Google Photos storage)
        
        Args:
            album_name: Not supported with Drive API (will be ignored)
            date_from: Optional start date (YYYY-MM-DD)
            date_to: Optional end date (YYYY-MM-DD)
        
        Returns:
            List of photo metadata dictionaries
        """
        if not self.service:
            print(f"{Fore.RED}Not authenticated with Google Drive")
            return []
        
        if album_name:
            print(f"{Fore.YELLOW}Warning: Album filtering not supported with Drive API")
        
        photos = []
        
        try:
            print(f"{Fore.CYAN}Fetching photos from Google Drive...")
            
            # Build query for image files
            # mimeType contains 'image/' for all image types
            query = "mimeType contains 'image/'"
            
            # Add date filter if provided
            if date_from:
                query += f" and createdTime >= '{date_from}T00:00:00'"
            if date_to:
                query += f" and createdTime <= '{date_to}T23:59:59'"
            
            # Query for photos
            page_token = None
            batch_count = 0
            
            while True:
                batch_count += 1
                
                try:
                    results = self.service.files().list(
                        q=query,
                        spaces='drive',
                        fields='nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, size, imageMediaMetadata, webContentLink, thumbnailLink)',
                        pageSize=100,
                        pageToken=page_token
                    ).execute()
                    
                    items = results.get('files', [])
                    
                    # Process items
                    for item in items:
                        metadata = item.get('imageMediaMetadata', {})
                        
                        photos.append({
                            'id': item['id'],
                            'filename': item.get('name', 'unknown'),
                            'url': item.get('webContentLink', ''),
                            'thumbnail': item.get('thumbnailLink', ''),
                            'mimeType': item.get('mimeType', ''),
                            'createdTime': item.get('createdTime', ''),
                            'modifiedTime': item.get('modifiedTime', ''),
                            'size': int(item.get('size', 0)),
                            'width': int(metadata.get('width', 0)),
                            'height': int(metadata.get('height', 0)),
                        })
                    
                    print(f"{Fore.CYAN}Batch {batch_count}: Found {len(photos)} photos so far...")
                    
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
                        
                except HttpError as e:
                    print(f"{Fore.RED}Google Drive API error: {e}")
                    break
            
            print(f"{Fore.GREEN}✓ Found {len(photos)} photos total")
            return photos
            
        except Exception as e:
            print(f"{Fore.RED}Error listing photos: {e}")
            return []
    
    def download_photo(self, photo_id: str, output_path: Path) -> bool:
        """
        Download a photo from Google Drive
        
        Args:
            photo_id: Drive file ID
            output_path: Local path to save the photo
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import io
            from googleapiclient.http import MediaIoBaseDownload
            
            request = self.service.files().get_media(fileId=photo_id)
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            return True
            
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Failed to download photo: {e}")
            return False
    
    def delete_photo(self, photo_id: str) -> bool:
        """
        Delete (trash) a photo in Google Drive
        
        Args:
            photo_id: Drive file ID
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Move file to trash (doesn't permanently delete)
            self.service.files().delete(fileId=photo_id).execute()
            return True
            
        except HttpError as e:
            print(f"{Fore.RED}Error deleting photo {photo_id}: {e}")
            return False
        except Exception as e:
            print(f"{Fore.RED}Error deleting photo {photo_id}: {e}")
            return False


def create_google_drive_photos_client() -> Optional[GoogleDrivePhotosClient]:
    """
    Create and authenticate a Google Drive Photos client
    
    Returns:
        Authenticated GoogleDrivePhotosClient or None if failed
    """
    if not GOOGLE_DRIVE_AVAILABLE:
        print(f"{Fore.RED}Google Drive integration not available")
        print(f"{Fore.YELLOW}Install dependencies: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return None
    
    client = GoogleDrivePhotosClient()
    if client.authenticate():
        return client
    return None

