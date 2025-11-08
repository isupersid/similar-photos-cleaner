# Photo Cleaner 📸

A smart tool to group similar photos, identify the best quality image in each group, and delete duplicates to free up disk space. Works with both **local files** and **cloud storage** (Dropbox)!

## ✨ Features

- 🔍 **Smart Similarity Detection**: Uses perceptual hashing to find similar/duplicate photos
- 🏆 **Quality-Based Selection**: Automatically picks the best photo based on resolution, sharpness, and file size
- 📄 **Beautiful HTML Reports**: Auto-generated visual reports with thumbnails and quality metrics
- 🛡️ **Safe by Default**: Dry-run mode with preview before any deletions
- ☁️ **Cloud Integration**: Clean photos directly in Dropbox (no sync needed!)
- 📅 **Date Filtering**: Process photos incrementally by date range
- 🖼️ **HEIC/HEIF Support**: Works with iPhone photos and modern formats
- 🗑️ **Space Recovery**: Calculates and displays space saved
- 🎯 **Flexible Deletion**: Move to backup folder or cloud trash instead of permanent deletion

## 🚀 Installation

```bash
pip install -r requirements.txt
```

For iPhone/HEIC photo support:
```bash
pip install pillow-heif
```

## 📖 Usage

### Quick Start - Local Files

**Preview mode (default - safe, generates HTML report)**
```bash
python photocleaner.py /path/to/photos
```

This generates `photo_cleaner_report.html` with thumbnails showing what will be kept/deleted. Open it in your browser to review!

**Execute deletion (after reviewing the report)**
```bash
python photocleaner.py /path/to/photos --execute
```

### Date-Based Filtering (Incremental Cleanup)

Perfect for large photo libraries! Process photos month by month or year by year:

```bash
# Process only November 2025 photos
python photocleaner.py /path/to/photos --date-from 2025-11-01 --date-to 2025-11-30

# Process all photos from 2020 onwards
python photocleaner.py /path/to/photos --date-from 2020-01-01 --execute

# Process photos up to end of 2015
python photocleaner.py /path/to/photos --date-to 2015-12-31
```

### Dropbox Cloud Mode ☁️

Clean photos directly in Dropbox without downloading your entire library!

**One-time setup:**
```bash
# Show setup instructions
python photocleaner.py --dropbox-setup

# Follow the instructions to:
# 1. Create a Dropbox app (takes 2 minutes)
# 2. Get your app credentials
# 3. Save to dropbox_config.json
```

**Use Dropbox mode:**
```bash
# Preview - scans entire Dropbox
python photocleaner.py --dropbox

# Specific folder (e.g., Camera Uploads)
python photocleaner.py --dropbox --dropbox-folder "/Camera Uploads"

# With date filtering for incremental cleanup
python photocleaner.py --dropbox --dropbox-folder "/Camera Uploads" --date-from 2025-11-01 --date-to 2025-11-30

# Execute deletion (moves to PhotoCleaner_Deleted folder in Dropbox)
python photocleaner.py --dropbox --execute --date-from 2025-11-01 --date-to 2025-11-30
```

### Advanced Options

**Adjust similarity threshold (0-64, lower = more strict)**
```bash
python photocleaner.py /path/to/photos --threshold 10 --execute
```

**Interactive mode (confirm each group before deletion)**
```bash
python photocleaner.py /path/to/photos --interactive
```

**Move to backup instead of deleting**
```bash
python photocleaner.py /path/to/photos --execute --backup-dir ./backup
```

## 🎯 How It Works

1. **Scans** the directory (or Dropbox folder) for image files
   - Supports: JPG, PNG, HEIC, HEIF, GIF, BMP, TIFF, WebP
2. **Filters** by date range (if specified)
   - Extracts dates from EXIF metadata, filenames, or file modification time
3. **Computes** perceptual hashes for each image
   - Uses average hash algorithm for speed and accuracy
4. **Groups** similar images based on hash distance
   - Configurable threshold for strictness
5. **Scores** each image based on:
   - Resolution (megapixels) - 70% weight
   - Sharpness (Laplacian variance) - 25% weight
   - File size (as a tiebreaker) - 5% weight
6. **Generates HTML report** (in dry-run mode)
   - Visual thumbnails of all groups
   - Quality metrics for each photo
   - Shows which photos will be kept/deleted
7. **Keeps** the best image in each group
8. **Deletes** (or moves to backup/trash) the rest

## 🛡️ Safety Features

- **Dry-run by default**: Always generates a preview report first
- **HTML reports**: Review changes visually before executing
- **Backup mode**: Move files to backup directory instead of deleting
- **Cloud trash**: Dropbox photos moved to `PhotoCleaner_Deleted` folder (not permanently deleted)
- **Conservative date filtering**: If date can't be determined, photo is included (never accidentally skipped)
- **Never modifies originals**: Only identifies best photo and removes duplicates

## 📊 HTML Report

Every dry-run generates a beautiful HTML report showing:
- Summary statistics (groups found, files to delete, space to save)
- Visual thumbnails of all photos
- Quality scores and metrics
- Clear indicators of which photos will be kept (green) vs deleted (red)
- Clickable file link that opens directly in your browser

## 🎨 Supported Formats

- **Standard formats**: JPG, JPEG, PNG, GIF, BMP, TIFF, WebP
- **Modern formats**: HEIC, HEIF (iPhone photos)
- **All common photo formats** from phones and cameras

## 💡 Tips

### For Large Photo Libraries
- Use date filtering to process incrementally (month by month or year by year)
- Start with a small date range to test your settings
- Review HTML reports before executing deletion

### For Cloud Photos
- Dropbox mode downloads photos temporarily for analysis, then cleans up
- Only downloads photos matching your date range (efficient!)
- Photos are moved to trash folder, not permanently deleted

### Finding the Right Threshold
- Default threshold (15) works well for most cases
- Lower threshold (5-10) = stricter matching, only very similar photos grouped
- Higher threshold (20-30) = looser matching, more photos grouped together
- Generate reports with different thresholds to find what works for you

## 🔧 Configuration Files

- `dropbox_config.json`: Dropbox app credentials (created during setup)
- `.photocleaner_dropbox_cache.json`: Cached authentication (in home directory)
- `photo_cleaner_report.html`: Generated HTML report (in scanned directory)

## 📝 Examples

### Example 1: Clean local photos from 2023
```bash
python photocleaner.py ~/Pictures --date-from 2023-01-01 --date-to 2023-12-31
# Review the report, then:
python photocleaner.py ~/Pictures --date-from 2023-01-01 --date-to 2023-12-31 --execute
```

### Example 2: Incremental Dropbox cleanup (process 2020s photos month by month)
```bash
# January 2020
python photocleaner.py --dropbox --dropbox-folder "/Camera Uploads" --date-from 2020-01-01 --date-to 2020-01-31 --execute

# February 2020
python photocleaner.py --dropbox --dropbox-folder "/Camera Uploads" --date-from 2020-02-01 --date-to 2020-02-29 --execute

# ... repeat for each month
```

### Example 3: Conservative cleanup with backup
```bash
# Move duplicates to backup folder for manual review
python photocleaner.py /path/to/photos --execute --backup-dir ./photo_backup
```

## 🤝 Contributing

Feel free to open issues or submit pull requests!

## 📄 License

MIT License - feel free to use and modify!



