"""
Google Photos API Client for Photo Cleaner
Handles authentication and photo operations with Google Photos
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
    GOOGLE_PHOTOS_AVAILABLE = True
except ImportError:
    GOOGLE_PHOTOS_AVAILABLE = False


# Scopes required for Google Photos
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly',
          'https://www.googleapis.com/auth/photoslibrary.appendonly']


class GooglePhotosClient:
    """Client for interacting with Google Photos API"""
    
    def __init__(self):
        self.service = None
        self.creds = None
        self.token_path = Path.home() / '.photocleaner_google_token.pickle'
    
    def authenticate(self, credentials_file: str = 'google_photos_credentials.json') -> bool:
        """
        Authenticate with Google Photos
        
        Args:
            credentials_file: Path to OAuth 2.0 client credentials JSON file
        
        Returns:
            True if authentication successful, False otherwise
        """
        creds_path = Path(credentials_file)
        
        if not creds_path.exists():
            print(f"{Fore.RED}Error: Google Photos credentials file not found: {credentials_file}")
            print(f"{Fore.YELLOW}Run --google-photos-setup to see setup instructions")
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
                    print(f"{Fore.CYAN}Refreshing Google Photos access token...")
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"{Fore.YELLOW}Could not refresh token: {e}")
                    self.creds = None
            
            if not self.creds:
                try:
                    print(f"{Fore.CYAN}Opening browser for Google Photos authentication...")
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
            self.service = build('photoslibrary', 'v1', credentials=self.creds, static_discovery=False)
            print(f"{Fore.GREEN}✓ Successfully connected to Google Photos")
            return True
        except Exception as e:
            print(f"{Fore.RED}Failed to build Google Photos service: {e}")
            return False
    
    def list_photos(self, album_name: Optional[str] = None, 
                    date_from: Optional[str] = None, 
                    date_to: Optional[str] = None) -> List[Dict]:
        """
        List photos from Google Photos
        
        Args:
            album_name: Optional album name to filter by
            date_from: Optional start date (YYYY-MM-DD)
            date_to: Optional end date (YYYY-MM-DD)
        
        Returns:
            List of photo metadata dictionaries
        """
        if not self.service:
            print(f"{Fore.RED}Not authenticated with Google Photos")
            return []
        
        photos = []
        
        try:
            # Build date filter if provided
            filters = {}
            if date_from or date_to:
                date_filter = {'ranges': []}
                
                if date_from:
                    date_parts = date_from.split('-')
                    start_date = {
                        'year': int(date_parts[0]),
                        'month': int(date_parts[1]),
                        'day': int(date_parts[2])
                    }
                else:
                    start_date = {'year': 2000, 'month': 1, 'day': 1}
                
                if date_to:
                    date_parts = date_to.split('-')
                    end_date = {
                        'year': int(date_parts[0]),
                        'month': int(date_parts[1]),
                        'day': int(date_parts[2])
                    }
                else:
                    end_date = {'year': 2100, 'month': 12, 'day': 31}
                
                date_filter['ranges'].append({
                    'startDate': start_date,
                    'endDate': end_date
                })
                
                filters['dateFilter'] = date_filter
            
            # If album specified, find it first
            album_id = None
            if album_name:
                print(f"{Fore.CYAN}Searching for album: {album_name}")
                albums = []
                page_token = None
                
                while True:
                    results = self.service.albums().list(
                        pageSize=50,
                        pageToken=page_token
                    ).execute()
                    
                    albums.extend(results.get('albums', []))
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
                
                # Find matching album
                for album in albums:
                    if album['title'].lower() == album_name.lower():
                        album_id = album['id']
                        print(f"{Fore.GREEN}✓ Found album: {album_name}")
                        break
                
                if not album_id:
                    print(f"{Fore.YELLOW}Warning: Album '{album_name}' not found")
                    return []
            
            # Search for photos
            print(f"{Fore.CYAN}Fetching photos from Google Photos...")
            page_token = None
            batch_count = 0
            
            while True:
                batch_count += 1
                
                # Build request body
                request_body = {'pageSize': 100}
                
                if page_token:
                    request_body['pageToken'] = page_token
                
                if album_id:
                    request_body['albumId'] = album_id
                elif filters:
                    request_body['filters'] = filters
                
                # Make API request
                # Use search() when we have albumId or filters, list() otherwise
                if album_id or filters:
                    results = self.service.mediaItems().search(body=request_body).execute()
                else:
                    # list() doesn't use a body, just query parameters
                    list_params = {'pageSize': 100}
                    if page_token:
                        list_params['pageToken'] = page_token
                    results = self.service.mediaItems().list(**list_params).execute()
                
                items = results.get('mediaItems', [])
                
                # Filter and process items
                for item in items:
                    # Only include photos (not videos)
                    if 'photo' in item.get('mediaMetadata', {}):
                        metadata = item.get('mediaMetadata', {})
                        creation_time = metadata.get('creationTime', '')
                        
                        photos.append({
                            'id': item['id'],
                            'filename': item.get('filename', 'unknown'),
                            'url': item['baseUrl'],
                            'mimeType': item.get('mimeType', ''),
                            'creationTime': creation_time,
                            'width': int(metadata.get('width', 0)),
                            'height': int(metadata.get('height', 0)),
                        })
                
                print(f"{Fore.CYAN}Batch {batch_count}: Found {len(photos)} photos so far...")
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            print(f"{Fore.GREEN}✓ Found {len(photos)} photos total")
            return photos
            
        except HttpError as e:
            print(f"{Fore.RED}Google Photos API error: {e}")
            return []
        except Exception as e:
            print(f"{Fore.RED}Error listing photos: {e}")
            return []
    
    def download_photo(self, photo_url: str, output_path: Path) -> bool:
        """
        Download a photo from Google Photos
        
        Args:
            photo_url: Base URL of the photo
            output_path: Local path to save the photo
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import requests
            
            # Append download parameters to base URL
            download_url = f"{photo_url}=d"  # =d for download
            
            response = requests.get(download_url, timeout=30)
            response.raise_for_status()
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return True
            
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Failed to download photo: {e}")
            return False
    
    def delete_photo(self, photo_id: str) -> bool:
        """
        Delete (move to trash) a photo in Google Photos
        
        Note: This requires the photoslibrary.appendonly scope
        
        Args:
            photo_id: ID of the photo to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Note: Google Photos API doesn't have a direct delete endpoint
            # We need to use batchRemoveMediaItems from an album
            # Or the user needs to manually delete from trash
            print(f"{Fore.YELLOW}Note: Google Photos API doesn't support direct deletion")
            print(f"{Fore.YELLOW}Photo {photo_id} would need to be manually deleted")
            return False
            
        except Exception as e:
            print(f"{Fore.RED}Error deleting photo: {e}")
            return False


def setup_google_photos():
    """Show setup instructions for Google Drive integration"""
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}Google Drive Integration Setup")
    print(f"{Fore.CYAN}{'='*80}\n")
    
    print(f"{Fore.YELLOW}⚠️  IMPORTANT NOTE:")
    print(f"{Fore.YELLOW}This integrates with Google DRIVE, not Google Photos library.")
    print(f"{Fore.YELLOW}It will access photos uploaded to Drive folders, not photos.google.com")
    print(f"{Fore.YELLOW}For Google Photos library access, use Google Takeout instead.\n")
    
    print(f"{Fore.GREEN}Step 1: Create Google Cloud Project")
    print(f"{Fore.WHITE}1. Go to: https://console.cloud.google.com/")
    print(f"{Fore.WHITE}2. Create a new project (or select existing)")
    print(f"{Fore.WHITE}3. Name it something like 'Photo Cleaner'\n")
    
    print(f"{Fore.GREEN}Step 2: Enable Google Drive API")
    print(f"{Fore.WHITE}1. Go to: https://console.cloud.google.com/apis/library")
    print(f"{Fore.WHITE}2. Search for 'Google Drive API' (NOT Photos Library API)")
    print(f"{Fore.WHITE}3. Click 'Enable'\n")
    
    print(f"{Fore.GREEN}Step 3: Create OAuth 2.0 Credentials")
    print(f"{Fore.WHITE}1. Go to: https://console.cloud.google.com/apis/credentials")
    print(f"{Fore.WHITE}2. Click 'Create Credentials' → 'OAuth client ID'")
    print(f"{Fore.WHITE}3. Configure consent screen if needed:")
    print(f"{Fore.WHITE}   - User type: External")
    print(f"{Fore.WHITE}   - App name: Photo Cleaner")
    print(f"{Fore.WHITE}   - Add your email as test user")
    print(f"{Fore.WHITE}   - Add scopes:")
    print(f"{Fore.WHITE}     * https://www.googleapis.com/auth/drive.photos.readonly")
    print(f"{Fore.WHITE}     * https://www.googleapis.com/auth/drive")
    print(f"{Fore.WHITE}4. Create OAuth client ID:")
    print(f"{Fore.WHITE}   - Application type: Desktop app")
    print(f"{Fore.WHITE}   - Name: Photo Cleaner Desktop")
    print(f"{Fore.WHITE}5. Download the JSON file\n")
    
    print(f"{Fore.GREEN}Step 4: Save Credentials")
    print(f"{Fore.WHITE}1. Rename the downloaded file to: google_photos_credentials.json")
    print(f"{Fore.WHITE}2. Place it in this directory: {Path.cwd()}\n")
    
    print(f"{Fore.GREEN}Step 5: Install Required Package")
    print(f"{Fore.WHITE}pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client\n")
    
    print(f"{Fore.GREEN}Step 6: Test Connection")
    print(f"{Fore.WHITE}python photocleaner.py --google-photos --date-from 2025-12-01\n")
    
    print(f"{Fore.GREEN}✅ Features:")
    print(f"{Fore.WHITE}- Accesses photos uploaded to Google Drive folders")
    print(f"{Fore.WHITE}- Supports automated deletion (moves to Drive trash)")
    print(f"{Fore.WHITE}- Works with shared Drive folders\n")
    
    print(f"{Fore.YELLOW}📖 Full documentation: GOOGLE_PHOTOS_SETUP.md")
    print(f"{Fore.CYAN}{'='*80}\n")


def create_google_photos_client() -> Optional[GooglePhotosClient]:
    """
    Create and authenticate a Google Photos client
    
    Returns:
        Authenticated GooglePhotosClient or None if failed
    """
    if not GOOGLE_PHOTOS_AVAILABLE:
        print(f"{Fore.RED}Google Photos integration not available")
        print(f"{Fore.YELLOW}Install dependencies: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return None
    
    client = GooglePhotosClient()
    if client.authenticate():
        return client
    return None

