"""
Dropbox Integration for Photo Cleaner
Allows direct cleanup of photos in Dropbox cloud storage
"""

import json
import tempfile
import webbrowser
from pathlib import Path
from typing import List, Dict, Optional

import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox.exceptions import AuthError, ApiError
from colorama import Fore


class DropboxClient:
    """Client for interacting with Dropbox"""
    
    def __init__(self, app_key: str, app_secret: str, refresh_token: Optional[str] = None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self.dbx = None
        self.cache_file = Path.home() / '.photocleaner_dropbox_cache.json'
        
    def authenticate(self) -> bool:
        """
        Authenticate with Dropbox using OAuth2
        Much simpler than OneDrive!
        """
        print(f"{Fore.CYAN}Authenticating with Dropbox...")
        
        # Try to use cached refresh token
        if self.refresh_token:
            try:
                self.dbx = dropbox.Dropbox(
                    app_key=self.app_key,
                    app_secret=self.app_secret,
                    oauth2_refresh_token=self.refresh_token
                )
                # Test the connection
                self.dbx.users_get_current_account()
                print(f"{Fore.GREEN}Successfully authenticated from cache!")
                return True
            except AuthError:
                print(f"{Fore.YELLOW}Cached credentials expired, re-authenticating...")
        
        # Start OAuth flow
        auth_flow = DropboxOAuth2FlowNoRedirect(
            self.app_key,
            self.app_secret,
            token_access_type='offline'  # Get refresh token
        )
        
        authorize_url = auth_flow.start()
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.GREEN}To authenticate with Dropbox:")
        print(f"{Fore.YELLOW}1. Visit this URL:")
        print(f"{Fore.WHITE}   {authorize_url}")
        print(f"{Fore.YELLOW}2. Click 'Allow' (you may need to log in first)")
        print(f"{Fore.YELLOW}3. Copy the authorization code")
        print(f"{Fore.CYAN}{'='*80}\n")
        
        # Try to open browser automatically
        try:
            webbrowser.open(authorize_url)
            print(f"{Fore.GREEN}Browser opened automatically. If not, please visit the URL above.")
        except:
            print(f"{Fore.YELLOW}Please manually open the URL above.")
        
        # Get authorization code from user
        auth_code = input(f"\n{Fore.CYAN}Enter the authorization code: {Fore.WHITE}").strip()
        
        try:
            oauth_result = auth_flow.finish(auth_code)
            self.refresh_token = oauth_result.refresh_token
            
            # Save refresh token to cache
            self._save_cache()
            
            # Create Dropbox client
            self.dbx = dropbox.Dropbox(
                app_key=self.app_key,
                app_secret=self.app_secret,
                oauth2_refresh_token=self.refresh_token
            )
            
            print(f"{Fore.GREEN}Successfully authenticated!")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Authentication failed: {e}")
            return False
    
    def _save_cache(self):
        """Save refresh token to cache"""
        try:
            cache_data = {
                'app_key': self.app_key,
                'app_secret': self.app_secret,
                'refresh_token': self.refresh_token
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
            self.cache_file.chmod(0o600)  # Secure permissions
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not save cache: {e}")
    
    @staticmethod
    def _load_cache() -> Optional[Dict]:
        """Load cached credentials"""
        cache_file = Path.home() / '.photocleaner_dropbox_cache.json'
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def list_photos(self, folder_path: str = '', recursive: bool = True, 
                    date_from: Optional[str] = None, date_to: Optional[str] = None,
                    use_search_api: bool = False) -> List[Dict]:
        """
        List photos in Dropbox folder
        
        Args:
            folder_path: Path to folder in Dropbox ('' for root)
            recursive: Whether to search recursively
            date_from: Filter from date (YYYY-MM-DD format) - uses server-side filtering
            date_to: Filter to date (YYYY-MM-DD format) - uses server-side filtering
            use_search_api: If True, uses Dropbox Search API (experimental), else uses list+filter
        
        Returns:
            List of photo metadata dicts
        """
        # If date filtering requested, choose the method
        if date_from or date_to:
            if use_search_api:
                print(f"{Fore.YELLOW}[DEBUG] Using SEARCH API approach (experimental)")
                return self._list_photos_with_search_api(folder_path, date_from, date_to)
            else:
                print(f"{Fore.YELLOW}[DEBUG] Using LIST+FILTER approach (reliable)")
                return self._list_photos_with_date_filter(folder_path, date_from, date_to)
        
        # Otherwise use regular listing
        return self._list_photos_standard(folder_path, recursive)
    
    def _list_photos_with_search_api(self, folder_path: str, date_from: Optional[str], date_to: Optional[str]) -> List[Dict]:
        """
        List photos using Dropbox Search API (EXPERIMENTAL - for debugging)
        """
        print(f"{Fore.CYAN}Fetching photos from Dropbox folder: {folder_path or 'root'}...")
        print(f"{Fore.GREEN}[SEARCH API] Attempting server-side date filtering")
        print(f"{Fore.YELLOW}[DEBUG] Date range: {date_from} to {date_to}")
        
        photos = []
        
        # Image extensions
        image_extensions = ('.jpg', '.jpeg', '.png', '.heic', '.heif')  # Start with common ones
        
        try:
            # Build date filter query
            date_query = ""
            if date_from and date_to:
                date_query = f" modified:{date_from}..{date_to}"
            elif date_from:
                date_query = f" modified:{date_from}.."
            elif date_to:
                date_query = f" modified:..{date_to}"
            
            print(f"{Fore.YELLOW}[DEBUG] Date query string: '{date_query}'")
            
            # Try different search approaches
            print(f"{Fore.CYAN}[SEARCH API] Method 1: Searching by extension with date filter...")
            
            # Search for each image type
            for ext in image_extensions:
                query = f"*.{ext.lstrip('.')}{date_query}"
                print(f"{Fore.CYAN}[DEBUG] Query: '{query}'")
                print(f"{Fore.CYAN}[DEBUG] Path restriction: '{folder_path or '(none - searching all)'}'")
                
                try:
                    options = dropbox.files.SearchOptions(
                        path=folder_path if folder_path else None,
                        max_results=1000,
                        file_status=dropbox.files.FileStatus.active,
                        filename_only=False
                    )
                    
                    print(f"{Fore.CYAN}  Searching for {ext} files...", end='', flush=True)
                    result = self.dbx.files_search_v2(query, options=options)
                    
                    print(f" found {len(result.matches)} matches")
                    print(f"{Fore.YELLOW}[DEBUG] Has more: {result.has_more}")
                    
                    for match in result.matches:
                        metadata = match.metadata.get_metadata()
                        
                        if isinstance(metadata, dropbox.files.FileMetadata):
                            photo_info = {
                                'id': metadata.id,
                                'name': metadata.name,
                                'path': metadata.path_display,
                                'size': metadata.size,
                                'modified': metadata.client_modified,
                                'media_info': None
                            }
                            photos.append(photo_info)
                            print(f"{Fore.GREEN}[DEBUG]   - {metadata.name} (modified: {metadata.client_modified})")
                    
                    # Handle pagination
                    while result.has_more:
                        result = self.dbx.files_search_continue_v2(result.cursor)
                        print(f"{Fore.CYAN}  Continuation found {len(result.matches)} more matches")
                        
                        for match in result.matches:
                            metadata = match.metadata.get_metadata()
                            if isinstance(metadata, dropbox.files.FileMetadata):
                                photo_info = {
                                    'id': metadata.id,
                                    'name': metadata.name,
                                    'path': metadata.path_display,
                                    'size': metadata.size,
                                    'modified': metadata.client_modified,
                                    'media_info': None
                                }
                                photos.append(photo_info)
                    
                except ApiError as e:
                    print(f"\n{Fore.RED}[DEBUG] Search failed for {ext}: {e}")
                    print(f"{Fore.RED}[DEBUG] Error details: {e.error}")
            
            print(f"\n{Fore.GREEN}[SEARCH API] Total found: {len(photos)} photos")
            
            # If search returned nothing, try without date filter to see if it's the filter causing issues
            if len(photos) == 0:
                print(f"{Fore.YELLOW}[DEBUG] No results with date filter. Testing without date filter...")
                test_query = "*.jpg"
                try:
                    options = dropbox.files.SearchOptions(
                        path=folder_path if folder_path else None,
                        max_results=10,
                        file_status=dropbox.files.FileStatus.active,
                        filename_only=False
                    )
                    result = self.dbx.files_search_v2(test_query, options=options)
                    print(f"{Fore.YELLOW}[DEBUG] Without date filter: found {len(result.matches)} .jpg files")
                    if len(result.matches) > 0:
                        print(f"{Fore.RED}[DEBUG] The date filter syntax might be the problem!")
                        print(f"{Fore.YELLOW}[DEBUG] Sample file: {result.matches[0].metadata.get_metadata().name}")
                except Exception as e2:
                    print(f"{Fore.RED}[DEBUG] Test query also failed: {e2}")
            
            return photos
            
        except Exception as e:
            print(f"\n{Fore.RED}[SEARCH API] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _list_photos_with_date_filter(self, folder_path: str, date_from: Optional[str], date_to: Optional[str]) -> List[Dict]:
        """
        List photos with date filtering using efficient client-side filtering
        (Dropbox search API has limitations, so we filter during listing)
        """
        from datetime import datetime as dt
        
        print(f"{Fore.CYAN}Fetching photos from Dropbox folder: {folder_path or 'root'}...")
        print(f"{Fore.YELLOW}Filtering by date: {date_from} to {date_to}")
        print(f"{Fore.CYAN}Scanning folder and filtering (this is faster than downloading everything)...")
        
        # Parse date strings to datetime for comparison
        date_from_dt = dt.strptime(date_from, '%Y-%m-%d') if date_from else None
        date_to_dt = dt.strptime(date_to, '%Y-%m-%d') if date_to else None
        
        photos = []
        skipped = 0
        has_more = True
        cursor = None
        batch_count = 0
        
        # Image extensions to look for
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif')
        
        try:
            while has_more:
                batch_count += 1
                
                if cursor is None:
                    print(f"{Fore.CYAN}Scanning batch 1...", end='', flush=True)
                    result = self.dbx.files_list_folder(folder_path, recursive=True)
                else:
                    print(f"\r{Fore.CYAN}Scanning batch {batch_count}... Found {len(photos)} matching photos, skipped {skipped}", end='', flush=True)
                    result = self.dbx.files_list_folder_continue(cursor)
                
                for entry in result.entries:
                    # Check if it's a file (not a folder)
                    if isinstance(entry, dropbox.files.FileMetadata):
                        # Check if it's an image
                        if entry.name.lower().endswith(image_extensions):
                            # Filter by date
                            file_date = entry.client_modified
                            
                            # Strip time for comparison
                            file_date_only = file_date.replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            # Check if within date range
                            if date_from_dt and file_date_only < date_from_dt:
                                skipped += 1
                                continue
                            
                            if date_to_dt and file_date_only > date_to_dt:
                                skipped += 1
                                continue
                            
                            # Passed date filter, add to list
                            photo_info = {
                                'id': entry.id,
                                'name': entry.name,
                                'path': entry.path_display,
                                'size': entry.size,
                                'modified': entry.client_modified,
                                'media_info': None
                            }
                            photos.append(photo_info)
                
                has_more = result.has_more
                cursor = result.cursor if has_more else None
            
            print(f"\r{Fore.GREEN}✓ Found {len(photos)} photos matching date range (skipped {skipped} outside range)                    ")
            return photos
            
        except ApiError as e:
            print(f"\n{Fore.RED}Error fetching photos: {e}")
            return []
    
    def _list_photos_standard(self, folder_path: str, recursive: bool) -> List[Dict]:
        """
        Standard photo listing (used when no date filter or as fallback)
        """
        print(f"{Fore.CYAN}Fetching photos from Dropbox folder: {folder_path or 'root'}...")
        print(f"{Fore.YELLOW}This may take a moment for large folders...")
        
        photos = []
        has_more = True
        cursor = None
        batch_count = 0
        
        # Image extensions to look for
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif')
        
        try:
            while has_more:
                batch_count += 1
                
                if cursor is None:
                    print(f"{Fore.CYAN}Scanning Dropbox folder (batch 1)...", end='', flush=True)
                    if recursive:
                        result = self.dbx.files_list_folder(folder_path, recursive=True)
                    else:
                        result = self.dbx.files_list_folder(folder_path)
                else:
                    print(f"\r{Fore.CYAN}Scanning Dropbox folder (batch {batch_count})... {len(photos)} photos found so far", end='', flush=True)
                    result = self.dbx.files_list_folder_continue(cursor)
                
                for entry in result.entries:
                    # Check if it's a file (not a folder)
                    if isinstance(entry, dropbox.files.FileMetadata):
                        # Check if it's an image
                        if entry.name.lower().endswith(image_extensions):
                            photo_info = {
                                'id': entry.id,
                                'name': entry.name,
                                'path': entry.path_display,
                                'size': entry.size,
                                'modified': entry.client_modified,
                                'media_info': None
                            }
                            
                            # Try to get media info if available
                            if hasattr(entry, 'media_info') and entry.media_info:
                                if hasattr(entry.media_info, 'metadata'):
                                    media = entry.media_info.metadata
                                    if hasattr(media, 'time_taken'):
                                        photo_info['photo_taken'] = media.time_taken
                            
                            photos.append(photo_info)
                
                has_more = result.has_more
                cursor = result.cursor if has_more else None
            
            print(f"\r{Fore.GREEN}✓ Found {len(photos)} photos in Dropbox                              ")
            return photos
            
        except ApiError as e:
            print(f"\n{Fore.RED}Error fetching photos: {e}")
            return []
    
    def download_photo(self, path: str, local_path: Path) -> bool:
        """Download a photo to local path"""
        try:
            metadata, response = self.dbx.files_download(path)
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return True
        except ApiError as e:
            print(f"{Fore.YELLOW}Warning: Failed to download {path}: {e}")
            return False
    
    def delete_photo(self, path: str) -> bool:
        """Delete a photo from Dropbox"""
        try:
            self.dbx.files_delete_v2(path)
            return True
        except ApiError as e:
            print(f"{Fore.YELLOW}Warning: Failed to delete {path}: {e}")
            return False
    
    def move_photo_to_trash(self, path: str) -> bool:
        """
        Move a photo to a 'PhotoCleaner_Deleted' folder
        """
        try:
            # Ensure trash folder exists
            trash_folder = '/PhotoCleaner_Deleted'
            try:
                self.dbx.files_create_folder_v2(trash_folder)
            except ApiError as e:
                # Folder might already exist, that's fine
                if not e.error.is_path() or not e.error.get_path().is_conflict():
                    raise
            
            # Get filename from path
            filename = Path(path).name
            new_path = f"{trash_folder}/{filename}"
            
            # Handle name conflicts by adding numbers
            counter = 1
            while True:
                try:
                    self.dbx.files_move_v2(path, new_path)
                    return True
                except ApiError as e:
                    if e.error.is_to() and e.error.get_to().is_conflict():
                        # File exists, try with a number
                        stem = Path(filename).stem
                        suffix = Path(filename).suffix
                        new_path = f"{trash_folder}/{stem}_{counter}{suffix}"
                        counter += 1
                        if counter > 100:  # Safety limit
                            print(f"{Fore.RED}Too many naming conflicts for {filename}")
                            return False
                    else:
                        raise
        
        except ApiError as e:
            print(f"{Fore.YELLOW}Warning: Failed to move {path} to trash: {e}")
            return False


def setup_dropbox_app():
    """
    Helper function to guide users through setting up Dropbox integration
    """
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}Dropbox Integration Setup (Much Easier than OneDrive!)")
    print(f"{Fore.CYAN}{'='*80}\n")
    
    print(f"{Fore.YELLOW}To use Dropbox integration, follow these simple steps:")
    print(f"\n1. Go to: {Fore.WHITE}https://www.dropbox.com/developers/apps/create")
    print(f"\n2. Choose:")
    print(f"   {Fore.WHITE}• Scoped access")
    print(f"   {Fore.WHITE}• Full Dropbox (to access your entire Dropbox)")
    print(f"   {Fore.WHITE}• Give it a name like 'Photo Cleaner'")
    print(f"\n3. Click {Fore.WHITE}'Create app'")
    print(f"\n4. In the {Fore.WHITE}'Permissions'{Fore.YELLOW} tab, enable:")
    print(f"   {Fore.WHITE}• files.metadata.read")
    print(f"   {Fore.WHITE}• files.metadata.write")
    print(f"   {Fore.WHITE}• files.content.read")
    print(f"   {Fore.WHITE}• files.content.write")
    print(f"\n5. In the {Fore.WHITE}'Settings'{Fore.YELLOW} tab, copy:")
    print(f"   {Fore.WHITE}• App key")
    print(f"   {Fore.WHITE}• App secret")
    print(f"\n6. Save them to a file named {Fore.WHITE}'dropbox_config.json'{Fore.YELLOW} with content:")
    print(f'{Fore.WHITE}   {{')
    print(f'{Fore.WHITE}       "app_key": "your-app-key-here",')
    print(f'{Fore.WHITE}       "app_secret": "your-app-secret-here"')
    print(f'{Fore.WHITE}   }}')
    print(f"\n{Fore.GREEN}That's it! Much simpler than OneDrive!")
    print(f"{Fore.CYAN}{'='*80}\n")


def load_dropbox_config() -> Optional[Dict]:
    """Load Dropbox app credentials from config file"""
    config_file = Path('dropbox_config.json')
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            return config
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not load config: {e}")
    
    # Try to load from cache
    cache = DropboxClient._load_cache()
    if cache:
        return cache
    
    return None


def create_dropbox_client() -> Optional[DropboxClient]:
    """Create and authenticate Dropbox client"""
    config = load_dropbox_config()
    if not config:
        setup_dropbox_app()
        print(f"{Fore.RED}Please set up Dropbox configuration first.")
        return None
    
    app_key = config.get('app_key')
    app_secret = config.get('app_secret')
    refresh_token = config.get('refresh_token')
    
    if not app_key or not app_secret:
        print(f"{Fore.RED}Missing app_key or app_secret in configuration")
        return None
    
    client = DropboxClient(app_key, app_secret, refresh_token)
    if client.authenticate():
        return client
    
    return None

