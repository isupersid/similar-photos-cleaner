#!/usr/bin/env python3
"""
Photo Cleaner - Group similar photos and delete duplicates
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict

import imagehash
import numpy as np
from PIL import Image, ImageStat
from PIL.ExifTags import TAGS
from tqdm import tqdm
from colorama import init, Fore, Style

from html_report import HTMLReportGenerator

try:
    from dropbox_client import DropboxClient, setup_dropbox_app, create_dropbox_client
    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

# Register HEIF/HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    print(f"{Fore.YELLOW}Warning: pillow-heif not installed. HEIC/HEIF files will be skipped.")
    print(f"{Fore.YELLOW}Install with: pip install pillow-heif")

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'}


class PhotoAnalyzer:
    """Analyzes photos for similarity and quality"""
    
    def __init__(self, hash_size=16):
        self.hash_size = hash_size
        
    def compute_hash(self, image_path: Path) -> imagehash.ImageHash:
        """Compute perceptual hash for an image"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Use average hash for speed and accuracy balance
                return imagehash.average_hash(img, hash_size=self.hash_size)
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not process {image_path}: {e}")
            return None
    
    def compute_quality_score(self, image_path: Path) -> Dict[str, float]:
        """
        Compute quality metrics for an image
        Returns dict with resolution, sharpness, and overall score
        """
        try:
            with Image.open(image_path) as img:
                # Resolution score (megapixels)
                width, height = img.size
                megapixels = (width * height) / 1_000_000
                
                # Sharpness score (Laplacian variance)
                gray = img.convert('L')
                array = np.array(gray)
                laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
                
                # Compute Laplacian
                from scipy.ndimage import convolve
                lap = convolve(array.astype(float), laplacian)
                sharpness = lap.var()
                
                # File size in MB
                file_size = image_path.stat().st_size / (1024 * 1024)
                
                # Compute overall score (weighted combination)
                # Normalize sharpness (typical range 0-10000+)
                normalized_sharpness = min(sharpness / 1000, 10)
                
                # Overall score: resolution (70%), sharpness (25%), file size (5%)
                overall_score = (megapixels * 0.7) + (normalized_sharpness * 0.25) + (file_size * 0.05)
                
                return {
                    'resolution': megapixels,
                    'sharpness': sharpness,
                    'file_size': file_size,
                    'score': overall_score
                }
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not analyze {image_path}: {e}")
            return {
                'resolution': 0,
                'sharpness': 0,
                'file_size': 0,
                'score': 0
            }


class PhotoCleaner:
    """Main photo cleaning tool"""
    
    def __init__(self, directory: Path, threshold: int = 15, dry_run: bool = True, 
                 interactive: bool = False, backup_dir: Path = None,
                 date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                 dropbox_mode: bool = False, dropbox_folder: str = '',
                 use_search_api: bool = False, decisions_file: Optional[Path] = None):
        self.directory = directory
        self.threshold = threshold
        self.dry_run = dry_run
        self.interactive = interactive
        self.backup_dir = backup_dir
        self.date_from = date_from
        self.date_to = date_to
        self.dropbox_mode = dropbox_mode
        self.dropbox_folder = dropbox_folder
        self.use_search_api = use_search_api
        self.decisions_file = decisions_file
        self.custom_decisions = None
        self.analyzer = PhotoAnalyzer()
        self.dropbox_client = None
        self.temp_dir = None
        self.photo_metadata = {}  # Map temp paths to Dropbox metadata
        
        # Load custom decisions if provided
        if self.decisions_file:
            self.load_decisions()
    
    def load_decisions(self):
        """Load custom keep/delete decisions from JSON file"""
        import json
        
        print(f"{Fore.CYAN}Loading custom decisions from: {self.decisions_file}")
        try:
            with open(self.decisions_file, 'r') as f:
                self.custom_decisions = json.load(f)
            
            # Convert the decisions format for easier lookup
            # From: {"group_id": {"keep": [paths], "delete": [paths]}}
            # To: {path: action} for quick lookup
            self.decision_map = {}
            for group_id, actions in self.custom_decisions.items():
                for path in actions.get('keep', []):
                    self.decision_map[str(path)] = 'keep'
                for path in actions.get('delete', []):
                    self.decision_map[str(path)] = 'delete'
            
            print(f"{Fore.GREEN}✓ Loaded decisions for {len(self.custom_decisions)} groups")
            print(f"{Fore.YELLOW}⚠️  Using custom decisions instead of AI recommendations")
        except FileNotFoundError:
            print(f"{Fore.RED}Error: Decisions file not found: {self.decisions_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"{Fore.RED}Error: Invalid JSON in decisions file: {e}")
            sys.exit(1)
    
    def process_from_decisions(self):
        """Fast mode: Process deletions directly from JSON decisions file"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}⚡ FAST MODE: Processing from decisions file")
        print(f"{Fore.CYAN}{'='*80}\n")
        
        # Collect all files to delete from the decisions
        files_to_delete = []
        files_to_keep = []
        
        for group_id, actions in self.custom_decisions.items():
            keep_files = actions.get('keep', [])
            delete_files = actions.get('delete', [])
            
            files_to_keep.extend([Path(p) for p in keep_files])
            files_to_delete.extend([Path(p) for p in delete_files])
        
        print(f"{Fore.GREEN}Loaded decisions:")
        print(f"  • {len(self.custom_decisions)} groups")
        print(f"  • {len(files_to_keep)} files to keep")
        print(f"  • {len(files_to_delete)} files to delete")
        
        # Calculate space to save
        total_space = 0
        valid_files = []
        
        for file_path in files_to_delete:
            # For Dropbox mode, we need to check if file exists in Dropbox
            if self.dropbox_mode:
                # In Dropbox mode, paths are Dropbox paths
                valid_files.append(file_path)
                # We can't easily check size without downloading, so just add to list
            else:
                # For local files, verify they exist
                if file_path.exists():
                    total_space += file_path.stat().st_size
                    valid_files.append(file_path)
                else:
                    print(f"{Fore.YELLOW}⚠️  File not found (skipping): {file_path}")
        
        if not valid_files:
            print(f"{Fore.YELLOW}No valid files to delete found!")
            return
        
        print(f"\n{Fore.CYAN}Space to save: {self.format_size(total_space)}")
        
        if self.dry_run:
            print(f"\n{Fore.YELLOW}{'='*80}")
            print(f"{Fore.YELLOW}DRY RUN - No files will be deleted")
            print(f"{Fore.YELLOW}{'='*80}")
            print(f"{Fore.CYAN}Would delete {len(valid_files)} files")
            for file_path in valid_files[:10]:  # Show first 10
                print(f"  • {file_path}")
            if len(valid_files) > 10:
                print(f"  ... and {len(valid_files) - 10} more files")
            print(f"\n{Fore.GREEN}Run with --execute to perform actual deletion")
            return
        
        # Actually delete files
        print(f"\n{Fore.RED}{'='*80}")
        print(f"{Fore.RED}DELETING FILES...")
        print(f"{Fore.RED}{'='*80}\n")
        
        deleted_count = 0
        failed_count = 0
        space_freed = 0
        
        for file_path in valid_files:
            try:
                if self.dropbox_mode:
                    # Dropbox deletion
                    success = self.dropbox_client.move_photo_to_trash(str(file_path))
                    if success:
                        print(f"{Fore.GREEN}✓ Moved to Dropbox trash: {file_path}")
                    else:
                        raise Exception("Failed to move to trash")
                else:
                    # Local deletion
                    file_size = file_path.stat().st_size
                    
                    if self.backup_dir:
                        # Move to backup
                        backup_path = self.backup_dir / file_path.name
                        counter = 1
                        while backup_path.exists():
                            backup_path = self.backup_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
                            counter += 1
                        shutil.move(str(file_path), str(backup_path))
                        print(f"{Fore.GREEN}✓ Moved to backup: {file_path.name}")
                    else:
                        # Delete permanently
                        file_path.unlink()
                        print(f"{Fore.GREEN}✓ Deleted: {file_path.name}")
                    
                    space_freed += file_size
                
                deleted_count += 1
                
            except Exception as e:
                print(f"{Fore.RED}✗ Failed to delete {file_path}: {e}")
                failed_count += 1
        
        # Summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}DELETION SUMMARY")
        print(f"{Fore.CYAN}{'='*80}")
        print(f"{Fore.GREEN}✓ Successfully deleted: {deleted_count} files")
        if not self.dropbox_mode:
            print(f"{Fore.GREEN}✓ Space freed: {self.format_size(space_freed)}")
        if failed_count > 0:
            print(f"{Fore.RED}✗ Failed: {failed_count} files")
        print(f"{Fore.CYAN}{'='*80}\n")
    
    @staticmethod
    def extract_date_from_exif(image_path: Path) -> Optional[datetime]:
        """Extract date from EXIF metadata"""
        try:
            with Image.open(image_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']:
                            # Parse EXIF date format: "YYYY:MM:DD HH:MM:SS"
                            try:
                                return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                            except ValueError:
                                continue
        except Exception:
            pass
        return None
    
    @staticmethod
    def extract_date_from_filename(image_path: Path) -> Optional[datetime]:
        """
        Extract date from filename using common patterns
        Supports formats like:
        - 20251107_023639127_iOS.heic
        - 2025-11-07_image.jpg
        - IMG_20251107.jpg
        - photo_2025_11_07.png
        """
        filename = image_path.name
        
        # Common date patterns
        patterns = [
            r'(\d{4})(\d{2})(\d{2})',           # YYYYMMDD
            r'(\d{4})[_-](\d{2})[_-](\d{2})',   # YYYY-MM-DD or YYYY_MM_DD
            r'(\d{2})[_-](\d{2})[_-](\d{4})',   # MM-DD-YYYY or MM_DD_YYYY
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:  # YYYY format
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:  # MM-DD-YYYY format
                        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                    
                    # Validate date
                    if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        return datetime(year, month, day)
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def get_image_date(self, image_path: Path) -> Optional[datetime]:
        """
        Get the date of an image, trying EXIF first, then filename, then file modification time
        """
        # Try EXIF first (most accurate)
        date = self.extract_date_from_exif(image_path)
        if date:
            return date
        
        # Try filename
        date = self.extract_date_from_filename(image_path)
        if date:
            return date
        
        # Fallback to file modification time
        try:
            timestamp = image_path.stat().st_mtime
            return datetime.fromtimestamp(timestamp)
        except Exception:
            return None
    
    def is_within_date_range(self, image_path: Path) -> bool:
        """Check if image is within the specified date range"""
        if not self.date_from and not self.date_to:
            return True  # No date filter
        
        image_date = self.get_image_date(image_path)
        if not image_date:
            # If we can't determine date, include it (conservative approach)
            return True
        
        # Strip time component for comparison
        image_date = image_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if self.date_from and image_date < self.date_from:
            return False
        
        if self.date_to and image_date > self.date_to:
            return False
        
        return True
        
    def find_images(self) -> List[Path]:
        """Find all image files in directory (or Dropbox)"""
        if self.dropbox_mode:
            return self.find_dropbox_images()
        
        print(f"{Fore.CYAN}Scanning for images in {self.directory}...")
        if self.date_from or self.date_to:
            date_range_str = ""
            if self.date_from:
                date_range_str += f"from {self.date_from.strftime('%Y-%m-%d')} "
            if self.date_to:
                date_range_str += f"to {self.date_to.strftime('%Y-%m-%d')}"
            print(f"{Fore.CYAN}Filtering images {date_range_str}...")
        
        images = []
        skipped = 0
        
        for root, dirs, files in os.walk(self.directory):
            for file in files:
                if Path(file).suffix.lower() in IMAGE_EXTENSIONS:
                    img_path = Path(root) / file
                    if self.is_within_date_range(img_path):
                        images.append(img_path)
                    else:
                        skipped += 1
        
        print(f"{Fore.GREEN}Found {len(images)} images in date range")
        if skipped > 0:
            print(f"{Fore.YELLOW}Skipped {skipped} images outside date range")
        return images
    
    def find_dropbox_images(self) -> List[Path]:
        """Find and download images from Dropbox"""
        print(f"{Fore.CYAN}Fetching images from Dropbox folder: {self.dropbox_folder or 'root'}")
        
        # Show which method is being used
        if self.use_search_api:
            print(f"{Fore.YELLOW}⚠️  Using experimental Search API for date filtering")
        
        # Convert date filters to string format for Dropbox API
        date_from_str = self.date_from.strftime('%Y-%m-%d') if self.date_from else None
        date_to_str = self.date_to.strftime('%Y-%m-%d') if self.date_to else None
        
        # Get list of photos from Dropbox (with date filtering if specified)
        photos = self.dropbox_client.list_photos(
            self.dropbox_folder, 
            date_from=date_from_str,
            date_to=date_to_str,
            use_search_api=self.use_search_api
        )
        
        if not photos:
            print(f"{Fore.YELLOW}No photos found matching criteria")
            return []
        
        # Note: When date filtering is used, photos are already filtered on server side!
        # Only do additional filename-based filtering if we got results without date filter
        if not self.date_from and not self.date_to:
            # No filtering needed
            pass
        else:
            # Photos are already filtered by Dropbox search API
            # But let's do a client-side double-check for filename-based dates
            # (in case Dropbox modified date doesn't match the actual photo date)
            print(f"{Fore.CYAN}Verifying dates from filenames...")
            
            verified_photos = []
            skipped = 0
            
            for photo in photos:
                # Try to extract from filename as additional check
                temp_path = Path(photo['name'])
                filename_date = self.extract_date_from_filename(temp_path)
                
                # If we found a date in filename, verify it's in range
                if filename_date:
                    filename_date = filename_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    if self.date_from and filename_date < self.date_from:
                        skipped += 1
                        continue
                    
                    if self.date_to and filename_date > self.date_to:
                        skipped += 1
                        continue
                
                verified_photos.append(photo)
            
            photos = verified_photos
            if skipped > 0:
                print(f"{Fore.YELLOW}Filtered out {skipped} additional photos based on filename dates")
            print(f"{Fore.GREEN}Final count: {len(photos)} images match all criteria")
        
        if not photos:
            print(f"{Fore.YELLOW}No photos match the criteria")
            return []
        
        # Create temporary directory for downloads
        self.temp_dir = tempfile.mkdtemp(prefix='photocleaner_')
        print(f"{Fore.CYAN}Downloading {len(photos)} photos to temporary directory for analysis...")
        
        downloaded_images = []
        
        for photo in tqdm(photos, desc="Downloading"):
            # Use just the filename for temp path
            temp_path = Path(self.temp_dir) / photo['name']
            if self.dropbox_client.download_photo(photo['path'], temp_path):
                downloaded_images.append(temp_path)
                # Store metadata for later deletion
                self.photo_metadata[str(temp_path)] = photo
        
        print(f"{Fore.GREEN}Downloaded {len(downloaded_images)} images from Dropbox")
        return downloaded_images
    
    def group_similar_images(self, images: List[Path]) -> List[List[Path]]:
        """Group similar images based on perceptual hash"""
        print(f"{Fore.CYAN}Computing perceptual hashes...")
        
        # Compute hashes
        image_hashes = {}
        for img_path in tqdm(images, desc="Hashing images"):
            hash_val = self.analyzer.compute_hash(img_path)
            if hash_val is not None:
                image_hashes[img_path] = hash_val
        
        print(f"{Fore.CYAN}Grouping similar images...")
        
        # Group images by similarity
        groups = []
        processed = set()
        
        image_list = list(image_hashes.items())
        
        for i, (img1, hash1) in enumerate(tqdm(image_list, desc="Grouping")):
            if img1 in processed:
                continue
            
            group = [img1]
            processed.add(img1)
            
            # Find similar images
            for img2, hash2 in image_list[i+1:]:
                if img2 in processed:
                    continue
                
                # Compute hash distance
                distance = hash1 - hash2
                
                if distance <= self.threshold:
                    group.append(img2)
                    processed.add(img2)
            
            # Only add groups with more than one image
            if len(group) > 1:
                groups.append(group)
        
        print(f"{Fore.GREEN}Found {len(groups)} groups of similar images")
        return groups
    
    def select_best_image(self, group: List[Path]) -> Tuple[Path, List[Path]]:
        """Select the best image from a group based on quality or custom decisions"""
        
        # If custom decisions are loaded, use them
        if self.custom_decisions:
            keep_files = []
            delete_files = []
            
            for img_path in group:
                path_str = str(img_path)
                action = self.decision_map.get(path_str)
                
                if action == 'keep':
                    keep_files.append(img_path)
                elif action == 'delete':
                    delete_files.append(img_path)
                else:
                    # If not in decisions (shouldn't happen), default to delete
                    delete_files.append(img_path)
            
            # Validate: must have at least one keep
            if not keep_files:
                print(f"{Fore.RED}Warning: No 'keep' file found in group with custom decisions")
                print(f"{Fore.YELLOW}Falling back to AI selection for this group")
                # Fall through to AI selection
            else:
                # Return first keep file as "best" (order doesn't matter since user chose)
                best_image = keep_files[0]
                # Add remaining keep files to delete list? No, keep them all
                # Actually, the process expects one best and rest to delete
                # So we need to pick one "best" from keeps and rest go to... keep list
                # Actually looking at the code, this returns (best, to_delete)
                # So we should return one keep and all deletes
                # But what if user marked multiple as keep? We should keep all of them!
                
                # Let me reconsider: the function returns (best_image, to_delete)
                # But if user wants to keep multiple, we need to handle that
                # For now, let's keep the first as "best" and not delete the others
                to_delete_only = delete_files  # Only delete files marked as delete
                
                return best_image, to_delete_only
        
        # Otherwise use AI-based quality scoring
        scores = {}
        
        for img_path in group:
            quality = self.analyzer.compute_quality_score(img_path)
            scores[img_path] = quality
        
        # Sort by score (descending)
        sorted_images = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
        
        best_image = sorted_images[0][0]
        to_delete = [img for img, _ in sorted_images[1:]]
        
        return best_image, to_delete
    
    def format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def process_groups(self, groups: List[List[Path]]):
        """Process groups and delete duplicates"""
        total_deleted = 0
        total_space_saved = 0
        
        for idx, group in enumerate(groups, 1):
            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}Group {idx}/{len(groups)} - {len(group)} similar images")
            print(f"{Fore.CYAN}{'='*80}")
            
            # Select best image
            best_image, to_delete = self.select_best_image(group)
            
            # Show group details
            print(f"{Fore.GREEN}✓ KEEP: {best_image.name}")
            best_quality = self.analyzer.compute_quality_score(best_image)
            print(f"  Resolution: {best_quality['resolution']:.2f} MP, "
                  f"Sharpness: {best_quality['sharpness']:.1f}, "
                  f"Size: {self.format_size(best_image.stat().st_size)}, "
                  f"Score: {best_quality['score']:.2f}")
            
            print(f"\n{Fore.RED}✗ DELETE ({len(to_delete)} files):")
            group_space = 0
            for img_path in to_delete:
                file_size = img_path.stat().st_size
                group_space += file_size
                quality = self.analyzer.compute_quality_score(img_path)
                print(f"  - {img_path.name} "
                      f"({self.format_size(file_size)}, "
                      f"Score: {quality['score']:.2f})")
            
            print(f"\n{Fore.YELLOW}Space to be saved: {self.format_size(group_space)}")
            
            # Interactive confirmation
            if self.interactive:
                response = input(f"\n{Fore.YELLOW}Delete these files? [y/N]: ").lower()
                if response != 'y':
                    print(f"{Fore.YELLOW}Skipped group {idx}")
                    continue
            
            # Delete or backup files
            if not self.dry_run:
                for img_path in to_delete:
                    try:
                        if self.dropbox_mode:
                            # Delete from Dropbox
                            metadata = self.dropbox_metadata.get(str(img_path))
                            if metadata:
                                if self.backup_dir or True:  # Always use "trash" for Dropbox
                                    success = self.dropbox_client.move_photo_to_trash(metadata['path'])
                                    if success:
                                        print(f"{Fore.BLUE}  Moved to Dropbox trash: {img_path.name}")
                                        total_deleted += 1
                                    else:
                                        print(f"{Fore.RED}  Error moving {img_path.name} to trash")
                                else:
                                    success = self.dropbox_client.delete_photo(metadata['path'])
                                    if success:
                                        print(f"{Fore.RED}  Deleted from Dropbox: {img_path.name}")
                                        total_deleted += 1
                                    else:
                                        print(f"{Fore.RED}  Error deleting {img_path.name}")
                        elif self.backup_dir:
                            # Move to backup directory
                            backup_path = self.backup_dir / img_path.name
                            # Handle name conflicts
                            counter = 1
                            while backup_path.exists():
                                backup_path = self.backup_dir / f"{img_path.stem}_{counter}{img_path.suffix}"
                                counter += 1
                            shutil.move(str(img_path), str(backup_path))
                            print(f"{Fore.BLUE}  Moved to backup: {backup_path}")
                            total_deleted += 1
                        else:
                            # Delete permanently
                            img_path.unlink()
                            print(f"{Fore.RED}  Deleted: {img_path.name}")
                            total_deleted += 1
                        
                        total_space_saved += file_size
                    except Exception as e:
                        print(f"{Fore.RED}  Error processing {img_path}: {e}")
            
            total_space_saved += group_space
        
        # Summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}SUMMARY")
        print(f"{Fore.CYAN}{'='*80}")
        print(f"{Fore.GREEN}Groups processed: {len(groups)}")
        print(f"{Fore.YELLOW}Files to delete: {sum(len(g)-1 for g in groups)}")
        print(f"{Fore.YELLOW}Space to be saved: {self.format_size(total_space_saved)}")
        
        if self.dry_run:
            print(f"\n{Fore.YELLOW}DRY RUN - No files were actually deleted")
            print(f"{Fore.YELLOW}Run without --dry-run to perform the deletion")
        else:
            print(f"\n{Fore.GREEN}Successfully deleted {total_deleted} files")
            print(f"{Fore.GREEN}Saved {self.format_size(total_space_saved)}")
    
    def run(self):
        """Run the photo cleaner"""
        print(f"{Fore.CYAN}Photo Cleaner Starting...")
        
        # Handle Dropbox mode
        if self.dropbox_mode:
            if not DROPBOX_AVAILABLE:
                print(f"{Fore.RED}Error: Dropbox integration not available.")
                print(f"{Fore.YELLOW}Install dependencies: pip install dropbox")
                return
            
            print(f"{Fore.CYAN}Mode: Dropbox Cloud")
            print(f"{Fore.CYAN}Folder: {self.dropbox_folder or 'root'}")
            
            # Authenticate
            self.dropbox_client = create_dropbox_client()
            if not self.dropbox_client:
                print(f"{Fore.RED}Failed to authenticate with Dropbox")
                return
        else:
            print(f"{Fore.CYAN}Directory: {self.directory}")
            if not self.directory.exists():
                print(f"{Fore.RED}Error: Directory does not exist: {self.directory}")
                return
        
        print(f"{Fore.CYAN}Threshold: {self.threshold}")
        print(f"{Fore.CYAN}Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        if self.decisions_file:
            print(f"{Fore.YELLOW}⚡ FAST MODE: Using decisions from JSON (skipping AI analysis)")
        if self.date_from or self.date_to:
            date_info = []
            if self.date_from:
                date_info.append(f"From: {self.date_from.strftime('%Y-%m-%d')}")
            if self.date_to:
                date_info.append(f"To: {self.date_to.strftime('%Y-%m-%d')}")
            print(f"{Fore.CYAN}Date Range: {' | '.join(date_info)}")
        
        # Create backup directory if specified
        if self.backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            print(f"{Fore.CYAN}Backup directory: {self.backup_dir}")
        
        # FAST MODE: If decisions file provided, skip finding/grouping and go straight to deletion
        if self.decisions_file:
            self.process_from_decisions()
            
            # Cleanup temporary directory if Dropbox mode
            if self.dropbox_mode and self.temp_dir:
                try:
                    shutil.rmtree(self.temp_dir)
                    print(f"{Fore.CYAN}Cleaned up temporary files")
                except Exception as e:
                    print(f"{Fore.YELLOW}Warning: Could not clean up temp directory: {e}")
            return
        
        # NORMAL MODE: Find, analyze, and group images
        # Find images
        images = self.find_images()
        
        if not images:
            print(f"{Fore.YELLOW}No images found in directory")
            return
        
        # Group similar images
        groups = self.group_similar_images(images)
        
        if not groups:
            print(f"{Fore.GREEN}No duplicate or similar images found!")
            return
        
        # Generate HTML report (always in dry-run mode)
        if self.dry_run:
            # Prepare data for HTML report
            groups_data = []
            for group in groups:
                best_image, to_delete = self.select_best_image(group)
                keep_quality = self.analyzer.compute_quality_score(best_image)
                
                delete_data = []
                for img_path in to_delete:
                    quality = self.analyzer.compute_quality_score(img_path)
                    delete_data.append((img_path, quality))
                
                groups_data.append({
                    'keep': (best_image, keep_quality),
                    'delete': delete_data
                })
            
            # Generate report with default name
            report_path = self.directory / 'photo_cleaner_report.html'
            report_generator = HTMLReportGenerator(self.directory, self.threshold, self.dry_run)
            
            # Pass photo metadata for Dropbox mode
            if self.dropbox_mode:
                if report_generator.save(groups_data, report_path, self.photo_metadata):
                    file_url = f"file://{report_path.resolve()}"
                    print(f"\n{Fore.GREEN}{'='*80}")
                    print(f"{Fore.GREEN}HTML Report Generated!")
                    print(f"{Fore.GREEN}{'='*80}")
                    print(f"{Fore.CYAN}📄 Report location: {Fore.WHITE}{report_path.resolve()}")
                    print(f"{Fore.CYAN}🔗 Click to open: \033]8;;{file_url}\033\\{file_url}\033]8;;\033\\")
                    print(f"{Fore.YELLOW}⚠️  Note: Report contains Dropbox paths for use with --apply-decisions")
                    print(f"{Fore.GREEN}{'='*80}\n")
            else:
                if report_generator.save(groups_data, report_path):
                    file_url = f"file://{report_path.resolve()}"
                    print(f"\n{Fore.GREEN}{'='*80}")
                    print(f"{Fore.GREEN}HTML Report Generated!")
                    print(f"{Fore.GREEN}{'='*80}")
                    print(f"{Fore.CYAN}📄 Report location: {Fore.WHITE}{report_path.resolve()}")
                    print(f"{Fore.CYAN}🔗 Click to open: \033]8;;{file_url}\033\\{file_url}\033]8;;\033\\")
                    print(f"{Fore.GREEN}{'='*80}\n")
        
        # Process groups
        self.process_groups(groups)
        
        # Cleanup temporary directory if Dropbox mode
        if self.dropbox_mode and self.temp_dir:
            try:
                shutil.rmtree(self.temp_dir)
                print(f"{Fore.CYAN}Cleaned up temporary files")
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not clean up temp directory: {e}")


def main():
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
        """
    )
    
    parser.add_argument(
        'directory',
        type=str,
        nargs='?',
        default='.',
        help='Directory containing photos to clean (not needed for --dropbox mode)'
    )
    
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
    
    parser.add_argument(
        '--backup-dir',
        type=str,
        help='Move files to backup directory instead of deleting'
    )
    
    parser.add_argument(
        '--dropbox',
        action='store_true',
        help='Use Dropbox cloud storage instead of local directory'
    )
    
    parser.add_argument(
        '--dropbox-folder',
        type=str,
        default='',
        help='Dropbox folder to process (default: root folder, use "" for root or "/Camera Uploads" for specific folder)'
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
    
    parser.add_argument(
        '--apply-decisions',
        type=str,
        help='Apply custom keep/delete decisions from JSON file (generated from HTML report)'
    )
    
    args = parser.parse_args()
    
    # Show Dropbox setup if requested
    if args.dropbox_setup:
        if DROPBOX_AVAILABLE:
            setup_dropbox_app()
        else:
            print(f"{Fore.RED}Dropbox integration not available.")
            print(f"{Fore.YELLOW}Install dependencies: pip install dropbox")
        return
    
    # Convert paths
    directory = Path(args.directory).resolve() if not args.dropbox else Path.cwd()
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else None
    decisions_file = Path(args.apply_decisions).resolve() if args.apply_decisions else None
    
    # Validate decisions file
    if decisions_file and not decisions_file.exists():
        print(f"{Fore.RED}Error: Decisions file not found: {decisions_file}")
        sys.exit(1)
    
    # Parse date arguments
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
    
    # Dry run is default unless --execute or --interactive is specified
    dry_run = not (args.execute or args.interactive)
    
    # Create and run cleaner
    cleaner = PhotoCleaner(
        directory=directory,
        threshold=args.threshold,
        dry_run=dry_run,
        interactive=args.interactive,
        backup_dir=backup_dir,
        date_from=date_from,
        date_to=date_to,
        dropbox_mode=args.dropbox,
        dropbox_folder=args.dropbox_folder,
        use_search_api=args.use_search_api,
        decisions_file=decisions_file
    )
    
    try:
        cleaner.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()



