#!/usr/bin/env python3
"""
Command-line interface for Photo Cleaner
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from colorama import Fore

try:
    from dropbox_client import setup_dropbox_app, create_dropbox_client
    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

try:
    from google_photos_client import setup_google_photos, create_google_photos_client
    GOOGLE_PHOTOS_AVAILABLE = True
except ImportError:
    GOOGLE_PHOTOS_AVAILABLE = False

from storage_provider import LocalStorageProvider, DropboxStorageProvider, GooglePhotosStorageProvider


def create_parser():
    """Create and configure the argument parser"""
    parser = argparse.ArgumentParser(
        description='Group similar photos and delete duplicates to save disk space',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview mode (default - generates HTML report, no deletions)
  %(prog)s /path/to/photos

  # Execute deletion
  %(prog)s /path/to/photos --execute

  # Dropbox mode - setup first
  %(prog)s --dropbox-setup

  # Dropbox mode - clean photos from Dropbox cloud
  %(prog)s --dropbox

  # Dropbox mode with specific folder
  %(prog)s --dropbox --dropbox-folder "/Camera Uploads"

  # Dropbox mode with date filtering
  %(prog)s --dropbox --date-from 2025-11-01 --date-to 2025-11-30

  # Google Photos mode
  %(prog)s --google-photos

  # Google Photos with album
  %(prog)s --google-photos --google-photos-album "Vacation"

  # Process only photos from November 2025
  %(prog)s /path/to/photos --date-from 2025-11-01 --date-to 2025-11-30

  # Process photos from a specific date onwards
  %(prog)s /path/to/photos --date-from 2020-01-01 --execute

  # Process photos up to a specific date
  %(prog)s /path/to/photos --date-to 2015-12-31

  # Adjust similarity threshold
  %(prog)s /path/to/photos --threshold 10 --execute

  # Interactive mode (confirm each deletion)
  %(prog)s /path/to/photos --interactive

  # Move to backup instead of deleting
  %(prog)s /path/to/photos --execute --backup-dir ./backup

  # Apply custom decisions from HTML report
  %(prog)s --dropbox --apply-decisions photo_decisions.json --execute
        """
    )
    
    # Positional arguments
    parser.add_argument(
        'directory',
        type=str,
        nargs='?',
        default='.',
        help='Directory containing photos to clean (not needed for cloud modes)'
    )
    
    # Core options
    parser.add_argument(
        '--threshold',
        type=int,
        default=15,
        help='Similarity threshold (0-64, lower = more strict, default: 15)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute deletion (default is dry-run/preview mode)'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Confirm each group before deletion (implies --execute)'
    )
    
    # Date filtering
    parser.add_argument(
        '--date-from',
        type=str,
        help='Process images from this date onwards (format: YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--date-to',
        type=str,
        help='Process images up to this date (format: YYYY-MM-DD)'
    )
    
    # Backup option
    parser.add_argument(
        '--backup-dir',
        type=str,
        help='Move files to backup directory instead of deleting'
    )
    
    # Dropbox options
    parser.add_argument(
        '--dropbox',
        action='store_true',
        help='Use Dropbox cloud storage instead of local directory'
    )
    
    parser.add_argument(
        '--dropbox-folder',
        type=str,
        default='',
        help='Dropbox folder to process (default: root folder)'
    )
    
    parser.add_argument(
        '--dropbox-setup',
        action='store_true',
        help='Show Dropbox setup instructions'
    )
    
    parser.add_argument(
        '--use-search-api',
        action='store_true',
        help='[Dropbox only] Use Search API for date filtering (experimental/debug)'
    )
    
    # Google Photos options
    parser.add_argument(
        '--google-photos',
        action='store_true',
        help='Process photos from Google Photos instead of local directory'
    )
    
    parser.add_argument(
        '--google-photos-album',
        type=str,
        default='',
        help='Google Photos album to process (default: all photos)'
    )
    
    parser.add_argument(
        '--google-photos-setup',
        action='store_true',
        help='Show Google Photos setup instructions'
    )
    
    # Fast mode
    parser.add_argument(
        '--apply-decisions',
        type=str,
        help='Apply custom keep/delete decisions from JSON file (generated from HTML report)'
    )
    
    return parser


def validate_and_parse_dates(args):
    """Parse and validate date arguments"""
    date_from = None
    date_to = None
    
    if args.date_from:
        try:
            date_from = datetime.strptime(args.date_from, "%Y-%m-%d")
        except ValueError:
            print(f"{Fore.RED}Error: Invalid --date-from format. Use YYYY-MM-DD")
            sys.exit(1)
    
    if args.date_to:
        try:
            date_to = datetime.strptime(args.date_to, "%Y-%m-%d")
        except ValueError:
            print(f"{Fore.RED}Error: Invalid --date-to format. Use YYYY-MM-DD")
            sys.exit(1)
    
    if date_from and date_to and date_from > date_to:
        print(f"{Fore.RED}Error: --date-from must be before --date-to")
        sys.exit(1)
    
    return date_from, date_to


def validate_paths(args):
    """Validate and convert file paths"""
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else None
    decisions_file = Path(args.apply_decisions).resolve() if args.apply_decisions else None
    
    if decisions_file and not decisions_file.exists():
        print(f"{Fore.RED}Error: Decisions file not found: {decisions_file}")
        sys.exit(1)
    
    return backup_dir, decisions_file


def create_storage_provider(args):
    """Create the appropriate storage provider based on CLI arguments"""
    
    if args.dropbox:
        # Dropbox mode
        if not DROPBOX_AVAILABLE:
            print(f"{Fore.RED}Error: Dropbox integration not available.")
            print(f"{Fore.YELLOW}Install dependencies: pip install dropbox")
            sys.exit(1)
        
        # Authenticate
        dropbox_client = create_dropbox_client()
        if not dropbox_client:
            print(f"{Fore.RED}Failed to authenticate with Dropbox")
            sys.exit(1)
        
        return DropboxStorageProvider(
            dropbox_client,
            folder=args.dropbox_folder,
            use_search_api=args.use_search_api
        )
    
    elif args.google_photos:
        # Google Photos mode
        if not GOOGLE_PHOTOS_AVAILABLE:
            print(f"{Fore.RED}Error: Google Photos integration not available.")
            print(f"{Fore.YELLOW}Install dependencies: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            sys.exit(1)
        
        # Authenticate
        google_photos_client = create_google_photos_client()
        if not google_photos_client:
            print(f"{Fore.RED}Failed to authenticate with Google Photos")
            sys.exit(1)
        
        return GooglePhotosStorageProvider(
            google_photos_client,
            album=args.google_photos_album
        )
    
    else:
        # Local filesystem mode
        directory = Path(args.directory).resolve()
        return LocalStorageProvider(directory=directory)


def handle_setup_commands(args):
    """Handle setup commands and return True if a setup command was run"""
    
    # Show Dropbox setup if requested
    if args.dropbox_setup:
        if DROPBOX_AVAILABLE:
            setup_dropbox_app()
        else:
            print(f"{Fore.RED}Dropbox integration not available.")
            print(f"{Fore.YELLOW}Install dependencies: pip install dropbox")
        return True
    
    # Show Google Photos setup if requested
    if args.google_photos_setup:
        if GOOGLE_PHOTOS_AVAILABLE:
            setup_google_photos()
        else:
            print(f"{Fore.RED}Google Photos integration not available.")
            print(f"{Fore.YELLOW}Install dependencies: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return True
    
    return False


def parse_args():
    """Parse command-line arguments and return configuration"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle setup commands (exit after if handled)
    if handle_setup_commands(args):
        return None
    
    # Validate and parse arguments
    date_from, date_to = validate_and_parse_dates(args)
    backup_dir, decisions_file = validate_paths(args)
    
    # Determine dry-run mode
    dry_run = not (args.execute or args.interactive)
    
    # Create storage provider
    storage = create_storage_provider(args)
    
    # Return configuration dictionary
    return {
        'storage': storage,
        'threshold': args.threshold,
        'dry_run': dry_run,
        'interactive': args.interactive,
        'backup_dir': backup_dir,
        'date_from': date_from,
        'date_to': date_to,
        'decisions_file': decisions_file
    }

