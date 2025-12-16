# Google Drive Integration Setup

## ⚠️ Important Note About Google Photos

**As of March 31, 2025, Google deprecated the API scopes needed to access Google Photos libraries.**

This integration uses the **Google Drive API** to access photos stored in Google Drive, **NOT your Google Photos library**.

If you want to clean photos from your Google Photos library, use one of these alternatives:
- **Google Takeout**: Download your photos from https://takeout.google.com/ and run the cleaner locally
- **Local Sync**: If you have Google Photos synced to your computer, run the cleaner on the local folder

This integration is useful for:
- ✅ Photos uploaded to Google Drive folders
- ✅ Photos in shared Drive folders
- ✅ Images stored in your Drive (not in Google Photos)

## Quick Start

1. **Install dependencies:**
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

2. **See setup instructions:**
```bash
python photocleaner.py --google-photos-setup
```

3. **Follow the steps to:**
   - Create a Google Cloud project
   - Enable Google Drive API (not Photos Library API)
   - Create OAuth 2.0 credentials
   - Download credentials JSON file

4. **Use it:**
```bash
# Preview all images in Drive
python photocleaner.py --google-photos

# With date filtering (based on file creation date)
python photocleaner.py --google-photos --date-from 2025-12-01 --date-to 2025-12-31

# Execute deletion (moves to trash)
python photocleaner.py --google-photos --date-from 2025-12-01 --date-to 2025-12-31 --execute
```

## Important Notes

- ✅ **Automated deletion supported** - Files moved to Drive trash
- ✅ **Works with Drive files** - Images uploaded to Drive folders
- ❌ **Does NOT access Google Photos library** - Due to API deprecation
- 📅 **Date filtering** - Based on file `createdTime` in Drive
- 🔐 **OAuth required** - Browser authentication on first run
- 💾 **Credentials cached** - Stored in `~/.photocleaner_drive_token.pickle`

## Setup Instructions

### Step 1: Create Google Cloud Project

1. Go to: https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Name it something like 'Photo Cleaner'

### Step 2: Enable Google Drive API

1. Go to: https://console.cloud.google.com/apis/library
2. Search for **'Google Drive API'** (not Photos Library API)
3. Click **'Enable'**

### Step 3: Create OAuth 2.0 Credentials

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click **'Create Credentials'** → **'OAuth client ID'**
3. Configure consent screen if needed:
   - User type: **External**
   - App name: **Photo Cleaner**
   - Add your email
   - Add scopes:
     - `https://www.googleapis.com/auth/drive.photos.readonly`
     - `https://www.googleapis.com/auth/drive`
4. Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: **Photo Cleaner Desktop**
5. Download the JSON file

### Step 4: Save Credentials

1. Rename the downloaded file to: `google_photos_credentials.json`
2. Place it in the photocleaner directory

### Step 5: Test Connection

```bash
python photocleaner.py --google-photos --date-from 2025-12-01 --date-to 2025-12-31
```

On first run, a browser will open for authentication. Grant the requested permissions.

## What Gets Accessed

The tool will find:
- Images uploaded to your Google Drive
- Images in shared Drive folders (where you have access)
- Any image files (`image/*` MIME types) stored in Drive

It will **NOT** find:
- Photos in your Google Photos library (API deprecated March 2025)
- Photos not uploaded to Drive
- Photos only accessible through photos.google.com

## For Google Photos Library Access

**Recommended approach**: Use Google Takeout

1. Go to https://takeout.google.com/
2. Deselect all products
3. Select only **"Google Photos"**
4. Choose export format and size
5. Click **"Create export"**
6. Download when ready
7. Extract the archive
8. Run the cleaner locally:

```bash
python photocleaner.py /path/to/extracted/Google\ Photos --date-from 2025-01-01
```

This gives you full access to all your photos with much better performance!

## Troubleshooting

### No photos found
- Check if you actually have photos uploaded to Google Drive (not just in Google Photos)
- Try without date filters first to see all images
- Verify the Drive API is enabled in your Cloud Console

### Authentication errors
- Delete cached token: `rm ~/.photocleaner_drive_token.pickle`
- Re-run authentication
- Check that both required scopes are added to OAuth consent screen

### Insufficient permissions
- Make sure Google Drive API (not Photos Library API) is enabled
- Verify OAuth consent screen has the Drive scopes configured
- Check that your app is in "Testing" mode with your email as a test user

## See Also

- Full documentation in README.md
- Dropbox integration for automated deletion
- OneDrive integration
