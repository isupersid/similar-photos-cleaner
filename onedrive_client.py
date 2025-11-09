"""
OneDrive Client for Photo Cleaner
Handles authentication and file operations with Microsoft OneDrive
"""

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional

import requests
from colorama import Fore

try:
    from msal import PublicClientApplication
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False
    print(f"{Fore.YELLOW}Warning: msal not installed. OneDrive integration will not work.")
    print(f"{Fore.YELLOW}Install with: pip install msal")


# Microsoft Graph API endpoints
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Files.ReadWrite.All", "offline_access"]


class OneDriveClient:
    """Client for interacting with OneDrive via Microsoft Graph API"""
    
    def __init__(self, client_id: str, cache_file: str = ".photocleaner_onedrive_cache.json"):
        """
        Initialize OneDrive client
        
        Args:
            client_id: Microsoft App Client ID
            cache_file: Path to store refresh token cache
        """
        if not MSAL_AVAILABLE:
            raise ImportError("msal library not available. Install with: pip install msal")
        
        self.client_id = client_id
        self.cache_file = cache_file
        self.access_token = None
        self.app = PublicClientApplication(
            client_id,
            authority=AUTHORITY
        )
    
    def authenticate(self) -> bool:
        """
        Authenticate with OneDrive using device code flow
        
        Returns:
            True if authentication successful, False otherwise
        """
        print(f"{Fore.CYAN}Authenticating with OneDrive...")
        
        # Try to get token from cache first
        accounts = self.app.get_accounts()
        if accounts:
            print(f"{Fore.CYAN}Found cached account, attempting silent authentication...")
            result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self.access_token = result["access_token"]
                print(f"{Fore.GREEN}✓ Authentication successful (from cache)")
                return True
        
        # If no cache or cache expired, use device code flow
        print(f"{Fore.CYAN}Starting device code authentication flow...")
        flow = self.app.initiate_device_flow(scopes=SCOPES)
        
        if "user_code" not in flow:
            print(f"{Fore.RED}Failed to create device flow")
            return False
        
        print(f"\n{Fore.YELLOW}{'='*80}")
        print(f"{Fore.YELLOW}ONEDRIVE AUTHENTICATION")
        print(f"{Fore.YELLOW}{'='*80}")
        print(f"{Fore.CYAN}{flow['message']}")
        print(f"{Fore.YELLOW}{'='*80}\n")
        
        # Wait for user to authenticate
        result = self.app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            print(f"{Fore.GREEN}✓ Authentication successful!")
            return True
        else:
            print(f"{Fore.RED}Authentication failed: {result.get('error_description', 'Unknown error')}")
            return False
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """
        Make an authenticated request to Microsoft Graph API
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (will be appended to GRAPH_API_BASE)
            **kwargs: Additional arguments for requests
        
        Returns:
            Response object or None if failed
        """
        if not self.access_token:
            print(f"{Fore.RED}Not authenticated. Call authenticate() first.")
            return None
        
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {self.access_token}'
        
        url = f"{GRAPH_API_BASE}{endpoint}"
        
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            
            # Handle token expiration
            if response.status_code == 401:
                print(f"{Fore.YELLOW}Token expired, re-authenticating...")
                if self.authenticate():
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    response = requests.request(method, url, headers=headers, **kwargs)
                else:
                    return None
            
            return response
        except Exception as e:
            print(f"{Fore.RED}Request failed: {e}")
            return None
    
    def list_photos(self, folder: str = '', date_from: str = None, date_to: str = None) -> List[Dict]:
        """
        List photos from OneDrive folder
        
        Args:
            folder: Folder path (e.g., '/Photos', '' for root)
            date_from: Start date filter (YYYY-MM-DD format)
            date_to: End date filter (YYYY-MM-DD format)
        
        Returns:
            List of photo metadata dictionaries
        """
        print(f"{Fore.CYAN}Fetching photos from OneDrive folder: {folder or 'root'}...")
        
        # Build the API endpoint
        if folder:
            # Encode the folder path
            folder_path = folder.strip('/')
            endpoint = f"/me/drive/root:/{folder_path}:/children"
        else:
            endpoint = "/me/drive/root/children"
        
        photos = []
        next_link = None
        batch_count = 0
        
        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'}
        
        while True:
            batch_count += 1
            
            if next_link:
                # Use next page link directly
                response = requests.get(
                    next_link,
                    headers={'Authorization': f'Bearer {self.access_token}'}
                )
            else:
                # First request
                response = self._make_request('GET', endpoint)
            
            if not response or response.status_code != 200:
                print(f"{Fore.RED}Failed to fetch photos: {response.status_code if response else 'No response'}")
                break
            
            data = response.json()
            items = data.get('value', [])
            
            # Filter for images
            for item in items:
                if item.get('file'):  # It's a file, not a folder
                    name = item.get('name', '')
                    ext = Path(name).suffix.lower()
                    
                    if ext in image_extensions:
                        # Apply date filtering if specified
                        if date_from or date_to:
                            modified_str = item.get('lastModifiedDateTime', '')
                            if modified_str:
                                # Parse ISO datetime
                                try:
                                    from datetime import datetime
                                    modified_date = datetime.fromisoformat(modified_str.replace('Z', '+00:00'))
                                    modified_date_str = modified_date.strftime('%Y-%m-%d')
                                    
                                    if date_from and modified_date_str < date_from:
                                        continue
                                    if date_to and modified_date_str > date_to:
                                        continue
                                except:
                                    pass  # If parsing fails, include the file
                        
                        photos.append({
                            'name': name,
                            'id': item.get('id'),
                            'path': item.get('@microsoft.graph.downloadUrl', ''),
                            'size': item.get('size', 0),
                            'modified': item.get('lastModifiedDateTime', '')
                        })
            
            # Progress update
            print(f"{Fore.CYAN}Batch {batch_count}: Found {len(photos)} photos so far...", end='\r')
            
            # Check for next page
            next_link = data.get('@odata.nextLink')
            if not next_link:
                break
        
        print(f"\n{Fore.GREEN}Found {len(photos)} photos in OneDrive")
        return photos
    
    def download_photo(self, download_url: str, output_path: Path) -> bool:
        """
        Download a photo from OneDrive
        
        Args:
            download_url: Direct download URL from photo metadata
            output_path: Local path to save the photo
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(download_url, stream=True)
            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            else:
                print(f"{Fore.RED}Failed to download: {response.status_code}")
                return False
        except Exception as e:
            print(f"{Fore.RED}Download error: {e}")
            return False
    
    def delete_photo(self, item_id: str) -> bool:
        """
        Permanently delete a photo from OneDrive
        
        Args:
            item_id: OneDrive item ID
        
        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/me/drive/items/{item_id}"
        response = self._make_request('DELETE', endpoint)
        
        if response and response.status_code == 204:
            return True
        else:
            print(f"{Fore.RED}Failed to delete: {response.status_code if response else 'No response'}")
            return False
    
    def move_photo_to_trash(self, item_id: str, trash_folder: str = "PhotoCleanerTrash") -> bool:
        """
        Move a photo to a trash folder instead of permanent deletion
        
        Args:
            item_id: OneDrive item ID
            trash_folder: Name of trash folder (will be created if doesn't exist)
        
        Returns:
            True if successful, False otherwise
        """
        # First, ensure trash folder exists
        trash_id = self._ensure_trash_folder(trash_folder)
        if not trash_id:
            return False
        
        # Move the item
        endpoint = f"/me/drive/items/{item_id}"
        data = {
            "parentReference": {
                "id": trash_id
            }
        }
        
        response = self._make_request('PATCH', endpoint, json=data)
        
        if response and response.status_code == 200:
            return True
        else:
            print(f"{Fore.RED}Failed to move to trash: {response.status_code if response else 'No response'}")
            return False
    
    def _ensure_trash_folder(self, folder_name: str) -> Optional[str]:
        """
        Ensure trash folder exists, create if not
        
        Args:
            folder_name: Name of trash folder
        
        Returns:
            Folder ID if successful, None otherwise
        """
        # Try to find existing trash folder
        endpoint = "/me/drive/root/children"
        response = self._make_request('GET', endpoint)
        
        if response and response.status_code == 200:
            items = response.json().get('value', [])
            for item in items:
                if item.get('name') == folder_name and item.get('folder'):
                    return item.get('id')
        
        # Create trash folder if not found
        endpoint = "/me/drive/root/children"
        data = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        
        response = self._make_request('POST', endpoint, json=data)
        
        if response and response.status_code == 201:
            return response.json().get('id')
        
        return None


def setup_onedrive_app():
    """Interactive setup for OneDrive App registration"""
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}ONEDRIVE SETUP INSTRUCTIONS")
    print(f"{Fore.CYAN}{'='*80}\n")
    
    print(f"{Fore.YELLOW}Step 1: Register an App in Azure Portal")
    print("   1. Go to: https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade")
    print("   2. Click 'New registration'")
    print("   3. Name: PhotoCleaner (or any name)")
    print("   4. Supported account types: Personal Microsoft accounts only")
    print("   5. Redirect URI: Leave blank")
    print("   6. Click 'Register'\n")
    
    print(f"{Fore.YELLOW}Step 2: Configure API Permissions")
    print("   1. In your app, go to 'API permissions'")
    print("   2. Click 'Add a permission' → 'Microsoft Graph' → 'Delegated permissions'")
    print("   3. Add: Files.ReadWrite.All")
    print("   4. Click 'Add permissions'\n")
    
    print(f"{Fore.YELLOW}Step 3: Enable Public Client Flow")
    print("   1. Go to 'Authentication'")
    print("   2. Under 'Advanced settings' → 'Allow public client flows': YES")
    print("   3. Click 'Save'\n")
    
    print(f"{Fore.YELLOW}Step 4: Get Your Client ID")
    print("   1. Go to 'Overview'")
    print("   2. Copy the 'Application (client) ID'\n")
    
    print(f"{Fore.CYAN}{'='*80}\n")
    
    client_id = input(f"{Fore.GREEN}Enter your Client ID: ").strip()
    
    if client_id:
        config = {'client_id': client_id}
        config_file = Path('onedrive_config.json')
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n{Fore.GREEN}✓ Configuration saved to {config_file}")
        print(f"{Fore.CYAN}You can now use OneDrive mode with:")
        print(f"{Fore.WHITE}  python photocleaner.py --onedrive")
    else:
        print(f"\n{Fore.RED}Setup cancelled")


def create_onedrive_client() -> Optional[OneDriveClient]:
    """
    Create and authenticate OneDrive client
    
    Returns:
        Authenticated OneDriveClient or None if failed
    """
    config_file = Path('onedrive_config.json')
    
    if not config_file.exists():
        print(f"{Fore.RED}OneDrive not configured. Run setup first:")
        print(f"{Fore.YELLOW}  python photocleaner.py --onedrive-setup")
        return None
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        client_id = config.get('client_id')
        if not client_id:
            print(f"{Fore.RED}Invalid configuration file")
            return None
        
        client = OneDriveClient(client_id)
        
        if client.authenticate():
            return client
        else:
            return None
            
    except Exception as e:
        print(f"{Fore.RED}Failed to create OneDrive client: {e}")
        return None

