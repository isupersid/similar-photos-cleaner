"""
HTML Report Generator for Photo Cleaner
Generates beautiful, interactive HTML reports showing photo groupings and deletions
"""

import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List

from PIL import Image
from colorama import Fore


class HTMLReportGenerator:
    """Generates HTML reports for photo cleaning operations"""
    
    def __init__(self, directory: Path, threshold: int, dry_run: bool):
        self.directory = directory
        self.threshold = threshold
        self.dry_run = dry_run
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    @staticmethod
    def image_to_base64(image_path: Path, max_size: int = 300) -> str:
        """Convert image to base64 thumbnail for HTML embedding with correct EXIF orientation"""
        try:
            with Image.open(image_path) as img:
                # Apply EXIF orientation before any processing
                # This fixes images that appear rotated incorrectly
                try:
                    # Get EXIF data
                    exif = img.getexif()
                    if exif:
                        # EXIF orientation tag is 274 (0x0112)
                        orientation = exif.get(274)
                        
                        # Apply orientation transformations
                        if orientation == 2:
                            img = img.transpose(Image.FLIP_LEFT_RIGHT)
                        elif orientation == 3:
                            img = img.rotate(180, expand=True)
                        elif orientation == 4:
                            img = img.transpose(Image.FLIP_TOP_BOTTOM)
                        elif orientation == 5:
                            img = img.transpose(Image.FLIP_LEFT_RIGHT).rotate(270, expand=True)
                        elif orientation == 6:
                            img = img.rotate(270, expand=True)
                        elif orientation == 7:
                            img = img.transpose(Image.FLIP_LEFT_RIGHT).rotate(90, expand=True)
                        elif orientation == 8:
                            img = img.rotate(90, expand=True)
                except (AttributeError, KeyError, IndexError):
                    # No EXIF data or no orientation tag, continue without rotation
                    pass
                
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                # Create thumbnail
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Convert to base64
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                img_str = base64.b64encode(buffer.getvalue()).decode()
                return f"data:image/jpeg;base64,{img_str}"
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not create thumbnail for {image_path}: {e}")
            return ""
    
    def generate(self, groups_data: List[dict]) -> str:
        """
        Generate HTML report showing groups and deletions
        
        Args:
            groups_data: List of dicts with keys:
                - 'keep': tuple (path, quality_dict)
                - 'delete': list of tuples [(path, quality_dict), ...]
        """
        print(f"{Fore.CYAN}Generating HTML report...")
        
        # Calculate statistics
        total_files_to_delete = sum(len(g['delete']) for g in groups_data)
        total_space_saved = sum(
            sum(img[0].stat().st_size for img in g['delete'])
            for g in groups_data
        )
        total_images = sum(len(g['delete']) + 1 for g in groups_data)
        
        html_parts = []
        
        # HTML header with CSS
        html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo Cleaner Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        
        .header .timestamp {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 40px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .summary-card {{
            background: white;
            padding: 24px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        
        .summary-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .summary-card .number {{
            font-size: 2.5em;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 8px;
        }}
        
        .summary-card .label {{
            color: #6c757d;
            font-size: 0.95em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .groups {{
            padding: 40px;
        }}
        
        .group {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            margin-bottom: 30px;
            overflow: hidden;
            transition: box-shadow 0.2s;
        }}
        
        .group:hover {{
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        }}
        
        .group-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            font-size: 1.3em;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .delete-group-btn {{
            background: #dc3545;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.75em;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        .delete-group-btn:hover {{
            background: #c82333;
            transform: scale(1.05);
        }}
        
        .group-warning-badge {{
            background: #ff9800;
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.75em;
            font-weight: 700;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{
                opacity: 1;
            }}
            50% {{
                opacity: 0.7;
            }}
        }}
        
        .group-content {{
            padding: 30px;
        }}
        
        .image-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 24px;
            margin-top: 20px;
        }}
        
        .image-card {{
            background: white;
            border: 3px solid #e9ecef;
            border-radius: 12px;
            overflow: hidden;
            transition: all 0.3s;
        }}
        
        .image-card.keep {{
            border-color: #28a745;
            box-shadow: 0 4px 12px rgba(40, 167, 69, 0.2);
        }}
        
        .image-card.delete {{
            border-color: #dc3545;
            opacity: 0.85;
        }}
        
        .image-card:hover {{
            transform: scale(1.02);
        }}
        
        .image-header {{
            padding: 12px;
            font-weight: 600;
            color: white;
            text-align: center;
            font-size: 0.95em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .image-card.keep .image-header {{
            background: #28a745;
        }}
        
        .image-card.delete .image-header {{
            background: #dc3545;
        }}
        
        .image-thumbnail {{
            width: 100%;
            height: 200px;
            object-fit: contain;
            background: #f8f9fa;
            transition: transform 0.3s ease;
        }}
        
        .image-thumbnail.rotated-90 {{
            transform: rotate(90deg);
        }}
        
        .image-thumbnail.rotated-180 {{
            transform: rotate(180deg);
        }}
        
        .image-thumbnail.rotated-270 {{
            transform: rotate(270deg);
        }}
        
        .image-info {{
            padding: 16px;
            background: #f8f9fa;
        }}
        
        .image-filename {{
            font-size: 0.85em;
            color: #495057;
            margin-bottom: 12px;
            word-break: break-all;
            font-weight: 500;
        }}
        
        .image-stats {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            font-size: 0.8em;
        }}
        
        .stat {{
            padding: 6px 10px;
            background: white;
            border-radius: 6px;
            display: flex;
            justify-content: space-between;
        }}
        
        .stat-label {{
            color: #6c757d;
            font-weight: 500;
        }}
        
        .stat-value {{
            color: #212529;
            font-weight: 600;
        }}
        
        .score-badge {{
            display: inline-block;
            padding: 8px 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 20px;
            font-weight: 700;
            font-size: 1.1em;
            margin-top: 8px;
        }}
        
        .footer {{
            background: #212529;
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 0.9em;
        }}
        
        .warning-banner {{
            background: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 8px;
            padding: 16px 24px;
            margin-bottom: 20px;
            color: #856404;
            font-weight: 500;
        }}
        
        .action-buttons {{
            position: sticky;
            top: 20px;
            z-index: 1000;
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            margin-bottom: 20px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1em;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .btn-warning {{
            background: #ffc107;
            color: #856404;
        }}
        
        .toggle-btn {{
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 8px 16px;
            background: #6c757d;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            transition: all 0.2s;
            z-index: 10;
        }}
        
        .toggle-btn:hover {{
            background: #5a6268;
            transform: scale(1.05);
        }}
        
        .image-card.keep .toggle-btn {{
            background: #dc3545;
        }}
        
        .image-card.delete .toggle-btn {{
            background: #28a745;
        }}
        
        .rotate-btn {{
            position: absolute;
            top: 10px;
            left: 10px;
            padding: 8px 12px;
            background: #17a2b8;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            transition: all 0.2s;
            z-index: 10;
        }}
        
        .rotate-btn:hover {{
            background: #138496;
            transform: scale(1.05);
        }}
        
        .modified-badge {{
            position: absolute;
            top: 50px;
            right: 10px;
            background: #ff9800;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 700;
        }}
        
        @media (max-width: 768px) {{
            .image-grid {{
                grid-template-columns: 1fr;
            }}
            
            .header h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📸 Photo Cleaner Report</h1>
            <div class="timestamp">Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</div>
        </div>
        
        <div class="summary">
            <div class="summary-card">
                <div class="number">{len(groups_data)}</div>
                <div class="label">Groups Found</div>
            </div>
            <div class="summary-card">
                <div class="number">{total_files_to_delete}</div>
                <div class="label">Files to Delete</div>
            </div>
            <div class="summary-card">
                <div class="number">{self.format_size(total_space_saved)}</div>
                <div class="label">Space to Save</div>
            </div>
            <div class="summary-card">
                <div class="number">{total_images}</div>
                <div class="label">Total Images</div>
            </div>
        </div>
        
        <div class="groups">
""")
        
        if self.dry_run:
            html_parts.append("""
            <div class="warning-banner">
                ⚠️ <strong>DRY RUN MODE:</strong> This is a preview. You can modify the keep/delete decisions below, then export and run with --apply-decisions.
            </div>
            
            <div class="action-buttons">
                <button class="btn btn-primary" onclick="saveDecisions()">
                    💾 Save Decisions to File
                </button>
                <button class="btn btn-warning" onclick="resetDecisions()">
                    🔄 Reset All Changes
                </button>
                <div style="flex-grow: 1;"></div>
                <div style="padding: 12px; background: #e9ecef; border-radius: 8px;">
                    <strong>Modified groups:</strong> <span id="modifiedCount">0</span>
                </div>
            </div>
""")
        
        # Process each group
        for idx, group_data in enumerate(groups_data, 1):
            keep_path, keep_quality = group_data['keep']
            to_delete = group_data['delete']
            group_space = sum(img[0].stat().st_size for img in to_delete)
            
            html_parts.append(f"""
            <div class="group" data-group="{idx}">
                <div class="group-header">
                    <span>Group {idx} of {len(groups_data)}</span>
                    <div style="display: flex; align-items: center; gap: 20px;">
                        <span>{len(to_delete) + 1} similar images • {self.format_size(group_space)} to save</span>
                        <button class="delete-group-btn" onclick="deleteEntireGroup({idx})" title="Mark all images in this group for deletion">
                            🗑️ Delete Entire Group
                        </button>
                    </div>
                </div>
                <div class="group-content">
                    <div class="image-grid">
""")
            
            # Add best image (to keep)
            keep_thumbnail = self.image_to_base64(keep_path)
            
            # Use cloud path for data-path if available, otherwise use local path
            keep_data_path = keep_quality.get('cloud_path') or keep_quality.get('dropbox_path', keep_path)
            keep_cloud_id = keep_quality.get('cloud_id', '')
            
            html_parts.append(f"""
                        <div class="image-card keep" data-path="{keep_data_path}" data-id="{keep_cloud_id}" data-group="{idx}" data-size="{keep_path.stat().st_size}">
                            <button class="rotate-btn" onclick="rotateImage(this)" title="Rotate 90°">↻</button>
                            <button class="toggle-btn" onclick="toggleKeepDelete(this)">Change to Delete</button>
                            <div class="image-header">✓ Keep</div>
                            {f'<img class="image-thumbnail" src="{keep_thumbnail}" alt="{keep_path.name}" data-rotation="0">' if keep_thumbnail else ''}
                            <div class="image-info">
                                <div class="image-filename">{keep_path.name}</div>
                                <div class="image-stats">
                                    <div class="stat">
                                        <span class="stat-label">Resolution:</span>
                                        <span class="stat-value">{keep_quality['resolution']:.2f} MP</span>
                                    </div>
                                    <div class="stat">
                                        <span class="stat-label">Size:</span>
                                        <span class="stat-value">{self.format_size(keep_path.stat().st_size)}</span>
                                    </div>
                                    <div class="stat">
                                        <span class="stat-label">Sharpness:</span>
                                        <span class="stat-value">{keep_quality['sharpness']:.1f}</span>
                                    </div>
                                </div>
                                <div style="text-align: center;">
                                    <span class="score-badge">Score: {keep_quality['score']:.2f}</span>
                                </div>
                            </div>
                        </div>
""")
            
            # Add images to delete
            for img_path, quality in to_delete:
                thumbnail = self.image_to_base64(img_path)
                
                # Use cloud path for data-path if available, otherwise use local path
                img_data_path = quality.get('cloud_path') or quality.get('dropbox_path', img_path)
                img_cloud_id = quality.get('cloud_id', '')
                
                html_parts.append(f"""
                        <div class="image-card delete" data-path="{img_data_path}" data-id="{img_cloud_id}" data-group="{idx}" data-size="{img_path.stat().st_size}">
                            <button class="rotate-btn" onclick="rotateImage(this)" title="Rotate 90°">↻</button>
                            <button class="toggle-btn" onclick="toggleKeepDelete(this)">Change to Keep</button>
                            <div class="image-header">✗ Delete</div>
                            {f'<img class="image-thumbnail" src="{thumbnail}" alt="{img_path.name}" data-rotation="0">' if thumbnail else ''}
                            <div class="image-info">
                                <div class="image-filename">{img_path.name}</div>
                                <div class="image-stats">
                                    <div class="stat">
                                        <span class="stat-label">Resolution:</span>
                                        <span class="stat-value">{quality['resolution']:.2f} MP</span>
                                    </div>
                                    <div class="stat">
                                        <span class="stat-label">Size:</span>
                                        <span class="stat-value">{self.format_size(img_path.stat().st_size)}</span>
                                    </div>
                                    <div class="stat">
                                        <span class="stat-label">Sharpness:</span>
                                        <span class="stat-value">{quality['sharpness']:.1f}</span>
                                    </div>
                                </div>
                                <div style="text-align: center;">
                                    <span class="score-badge">Score: {quality['score']:.2f}</span>
                                </div>
                            </div>
                        </div>
""")
            
            html_parts.append("""
                    </div>
                </div>
            </div>
""")
        
        # Footer
        html_parts.append(f"""
        </div>
        
        <div class="footer">
            Generated by Photo Cleaner • Directory: {self.directory} • Threshold: {self.threshold}
        </div>
    </div>
    
    <script>
        // Track original decisions and modifications
        const originalDecisions = {{}};
        const modifiedGroups = new Set();
        
        // Initialize original decisions on page load
        document.addEventListener('DOMContentLoaded', function() {{
            document.querySelectorAll('.image-card').forEach(card => {{
                const path = card.getAttribute('data-path');
                const group = card.getAttribute('data-group');
                const action = card.classList.contains('keep') ? 'keep' : 'delete';
                
                if (!originalDecisions[group]) {{
                    originalDecisions[group] = {{}};
                }}
                originalDecisions[group][path] = action;
            }});
        }});
        
        function rotateImage(button) {{
            const card = button.closest('.image-card');
            const img = card.querySelector('.image-thumbnail');
            
            if (!img) return;
            
            // Get current rotation (default to 0)
            let currentRotation = parseInt(img.getAttribute('data-rotation') || '0');
            
            // Increment rotation by 90 degrees
            currentRotation = (currentRotation + 90) % 360;
            
            // Update the data attribute
            img.setAttribute('data-rotation', currentRotation);
            
            // Remove all rotation classes
            img.classList.remove('rotated-90', 'rotated-180', 'rotated-270');
            
            // Apply the appropriate rotation class
            if (currentRotation === 90) {{
                img.classList.add('rotated-90');
            }} else if (currentRotation === 180) {{
                img.classList.add('rotated-180');
            }} else if (currentRotation === 270) {{
                img.classList.add('rotated-270');
            }}
        }}
        
        function deleteEntireGroup(groupId) {{
            if (!confirm(`Are you sure you want to mark all images in Group ${{groupId}} for deletion?`)) {{
                return;
            }}
            
            // Find all cards in this group
            const groupCards = document.querySelectorAll(`[data-group="${{groupId}}"]`);
            
            // Mark all as delete
            groupCards.forEach(card => {{
                if (card.classList.contains('image-card')) {{
                    const header = card.querySelector('.image-header');
                    const button = card.querySelector('.toggle-btn');
                    
                    // Change to delete state
                    card.classList.remove('keep');
                    card.classList.add('delete');
                    header.textContent = '✗ Delete';
                    button.textContent = 'Change to Keep';
                    
                    // Add modified badge
                    if (!card.querySelector('.modified-badge')) {{
                        const badge = document.createElement('div');
                        badge.className = 'modified-badge';
                        badge.textContent = 'MODIFIED';
                        card.appendChild(badge);
                    }}
                }}
            }});
            
            // Mark group as modified
            modifiedGroups.add(String(groupId));
            updateModifiedCount();
            updateGroupWarnings(groupId);
        }}
        
        function toggleKeepDelete(button) {{
            const card = button.closest('.image-card');
            const group = card.getAttribute('data-group');
            const path = card.getAttribute('data-path');
            const header = card.querySelector('.image-header');
            
            // Toggle the state
            if (card.classList.contains('keep')) {{
                card.classList.remove('keep');
                card.classList.add('delete');
                header.textContent = '✗ Delete';
                button.textContent = 'Change to Keep';
            }} else {{
                card.classList.remove('delete');
                card.classList.add('keep');
                header.textContent = '✓ Keep';
                button.textContent = 'Change to Delete';
            }}
            
            // Add modified badge if not already there
            if (!card.querySelector('.modified-badge')) {{
                const badge = document.createElement('div');
                badge.className = 'modified-badge';
                badge.textContent = 'MODIFIED';
                card.appendChild(badge);
            }}
            
            // Track modification
            const currentAction = card.classList.contains('keep') ? 'keep' : 'delete';
            if (originalDecisions[group][path] !== currentAction) {{
                modifiedGroups.add(group);
            }} else {{
                // Check if any other files in this group are still modified
                let groupStillModified = false;
                for (const [p, origAction] of Object.entries(originalDecisions[group])) {{
                    const otherCard = document.querySelector(`[data-path="${{p}}"]`);
                    const currentOtherAction = otherCard.classList.contains('keep') ? 'keep' : 'delete';
                    if (origAction !== currentOtherAction) {{
                        groupStillModified = true;
                        break;
                    }}
                }}
                if (!groupStillModified) {{
                    modifiedGroups.delete(group);
                    card.querySelector('.modified-badge')?.remove();
                }}
            }}
            
            updateModifiedCount();
            updateGroupWarnings(group);
        }}
        
        function updateGroupWarnings(groupId) {{
            // Check if all images in this group are marked for deletion
            const groupCards = document.querySelectorAll(`.image-card[data-group="${{groupId}}"]`);
            const keepCount = Array.from(groupCards).filter(c => c.classList.contains('keep')).length;
            
            // Find the group container
            const groupContainer = document.querySelector(`.group[data-group="${{groupId}}"]`);
            if (!groupContainer) return;
            
            const groupHeader = groupContainer.querySelector('.group-header');
            let warningBadge = groupHeader.querySelector('.group-warning-badge');
            
            if (keepCount === 0) {{
                // All images marked for deletion - show warning
                if (!warningBadge) {{
                    warningBadge = document.createElement('span');
                    warningBadge.className = 'group-warning-badge';
                    warningBadge.textContent = '⚠️ ENTIRE GROUP WILL BE DELETED';
                    groupHeader.appendChild(warningBadge);
                }}
            }} else {{
                // At least one image to keep - remove warning
                if (warningBadge) {{
                    warningBadge.remove();
                }}
            }}
        }}
        
        function updateModifiedCount() {{
            document.getElementById('modifiedCount').textContent = modifiedGroups.size;
        }}
        
        function resetDecisions() {{
            if (!confirm('Reset all changes to original AI decisions?')) {{
                return;
            }}
            
            document.querySelectorAll('.image-card').forEach(card => {{
                const path = card.getAttribute('data-path');
                const group = card.getAttribute('data-group');
                const originalAction = originalDecisions[group][path];
                const header = card.querySelector('.image-header');
                const button = card.querySelector('.toggle-btn');
                
                card.classList.remove('keep', 'delete');
                card.classList.add(originalAction);
                
                if (originalAction === 'keep') {{
                    header.textContent = '✓ Keep';
                    button.textContent = 'Change to Delete';
                }} else {{
                    header.textContent = '✗ Delete';
                    button.textContent = 'Change to Keep';
                }}
                
                card.querySelector('.modified-badge')?.remove();
            }});
            
            modifiedGroups.clear();
            updateModifiedCount();
            
            // Update all group warnings
            const allGroups = new Set();
            document.querySelectorAll('.image-card').forEach(card => {{
                allGroups.add(card.getAttribute('data-group'));
            }});
            allGroups.forEach(groupId => updateGroupWarnings(groupId));
        }}
        
        function saveDecisions() {{
            const decisions = {{}};
            
            document.querySelectorAll('.image-card').forEach(card => {{
                const path = card.getAttribute('data-path');
                const cloudId = card.getAttribute('data-id');
                const group = card.getAttribute('data-group');
                const size = parseInt(card.getAttribute('data-size')) || 0;
                const action = card.classList.contains('keep') ? 'keep' : 'delete';
                
                if (!decisions[group]) {{
                    decisions[group] = {{keep: [], delete: []}};
                }}
                
                // Store path, size, and cloud_id (for OneDrive) as an object
                const item = {{path: path, size: size}};
                if (cloudId) {{
                    item.cloud_id = cloudId;
                }}
                decisions[group][action].push(item);
            }});
            
            // Create JSON file
            const dataStr = JSON.stringify(decisions, null, 2);
            const dataBlob = new Blob([dataStr], {{type: 'application/json'}});
            const url = URL.createObjectURL(dataBlob);
            
            // Create download link
            const link = document.createElement('a');
            link.href = url;
            link.download = 'photo_decisions.json';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            
            alert('Decisions saved to photo_decisions.json!\\n\\nTo apply these decisions, run:\\npython photocleaner.py --apply-decisions photo_decisions.json --execute');
        }}
    </script>
</body>
</html>
""")
        
        return ''.join(html_parts)
    
    def save(self, groups_data: List[dict], output_path: Path, photo_metadata: dict = None) -> bool:
        """
        Generate and save HTML report to file
        
        Args:
            groups_data: List of group dictionaries
            output_path: Path to save the HTML file
            photo_metadata: Optional dict mapping temp paths to cloud metadata (for Dropbox/OneDrive mode)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # If photo_metadata provided (cloud mode), replace temp paths with cloud paths
            if photo_metadata:
                groups_data = self._replace_with_cloud_paths(groups_data, photo_metadata)
            
            html_content = self.generate(groups_data)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"{Fore.GREEN}HTML report saved to: {output_path}")
            return True
        except Exception as e:
            print(f"{Fore.RED}Error saving HTML report: {e}")
            return False
    
    def generate_all_photos_report(self, image_paths: List[Path]) -> str:
        """
        Generate HTML report showing all photos found (when no duplicates exist)
        
        Args:
            image_paths: List of Path objects for all images found
        
        Returns:
            HTML content as string
        """
        print(f"{Fore.CYAN}Generating gallery of all photos found...")
        
        # Calculate statistics
        total_images = len(image_paths)
        total_size = sum(img.stat().st_size for img in image_paths)
        
        # Start building HTML
        html_parts = []
        html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo Cleaner - All Photos Found</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 3px solid #667eea;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            color: #2d3748;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            font-size: 1.2em;
            color: #718096;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }}
        
        .stat-card .number {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .stat-card .label {{
            font-size: 1em;
            opacity: 0.9;
        }}
        
        .info-box {{
            background: #e6fffa;
            border-left: 4px solid #38b2ac;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
        }}
        
        .info-box h3 {{
            color: #234e52;
            margin-bottom: 10px;
        }}
        
        .info-box p {{
            color: #2c7a7b;
            line-height: 1.6;
        }}
        
        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }}
        
        .photo-card {{
            background: #f7fafc;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            padding: 15px;
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        
        .photo-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            border-color: #667eea;
        }}
        
        .photo-card img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
            border-radius: 8px;
            margin-bottom: 10px;
        }}
        
        .photo-info {{
            font-size: 0.9em;
        }}
        
        .photo-name {{
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 5px;
            word-break: break-word;
        }}
        
        .photo-size {{
            color: #718096;
            font-size: 0.85em;
        }}
        
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #e2e8f0;
            text-align: center;
            color: #718096;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📸 Photo Cleaner Gallery</h1>
            <p class="subtitle">All Photos Found - No Duplicates Detected</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="number">{total_images}</div>
                <div class="label">Photos Found</div>
            </div>
            <div class="stat-card">
                <div class="number">{self.format_size(total_size)}</div>
                <div class="label">Total Size</div>
            </div>
            <div class="stat-card">
                <div class="number">0</div>
                <div class="label">Duplicates Found</div>
            </div>
        </div>
        
        <div class="info-box">
            <h3>✅ Great News!</h3>
            <p>No duplicate or similar images were found in your photo library. All {total_images} photos appear to be unique based on the similarity threshold of {self.threshold}.</p>
        </div>
        
        <h2 style="color: #2d3748; margin-bottom: 20px;">All Photos</h2>
        <div class="gallery">
""")
        
        # Add each photo
        for img_path in image_paths:
            try:
                file_size = img_path.stat().st_size
                thumbnail = self.image_to_base64(img_path, max_size=250)
                
                html_parts.append(f"""
            <div class="photo-card">
                <img src="{thumbnail}" alt="{img_path.name}" loading="lazy">
                <div class="photo-info">
                    <div class="photo-name" title="{img_path.name}">{img_path.name}</div>
                    <div class="photo-size">{self.format_size(file_size)}</div>
                </div>
            </div>
""")
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not add {img_path.name} to report: {e}")
        
        # Close HTML
        html_parts.append("""
        </div>
        
        <div class="footer">
            <p>Generated by Photo Cleaner on """ + datetime.now().strftime("%Y-%m-%d at %I:%M %p") + """</p>
            <p style="margin-top: 10px;">All photos are unique - no action needed! 🎉</p>
        </div>
    </div>
</body>
</html>
""")
        
        return ''.join(html_parts)
    
    def save_all_photos_report(self, image_paths: List[Path], output_path: Path) -> bool:
        """
        Generate and save gallery report showing all photos (no duplicates)
        
        Args:
            image_paths: List of Path objects for all images
            output_path: Path to save the HTML file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            html_content = self.generate_all_photos_report(image_paths)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"{Fore.GREEN}Gallery report saved to: {output_path}")
            return True
        except Exception as e:
            print(f"{Fore.RED}Error saving gallery report: {e}")
            return False
    
    def _replace_with_cloud_paths(self, groups_data: List[dict], photo_metadata: dict) -> List[dict]:
        """Replace temp file paths with cloud paths (Dropbox/OneDrive) for cloud mode"""
        updated_groups = []
        
        for group in groups_data:
            # Keep path: store both temp path (for image reading) and cloud path (for JSON)
            keep_temp_path, keep_quality = group['keep']
            metadata = photo_metadata.get(str(keep_temp_path), {})
            cloud_keep_path = metadata.get('path', str(keep_temp_path))
            
            # Store temp path for image reading, but add cloud_path to quality dict
            keep_quality_with_path = keep_quality.copy()
            # Use generic 'cloud_path' and 'cloud_id' keys for both Dropbox and OneDrive
            keep_quality_with_path['cloud_path'] = cloud_keep_path
            # Also support legacy 'dropbox_path' key for backward compatibility
            keep_quality_with_path['dropbox_path'] = cloud_keep_path
            
            # Store item ID if available (needed for OneDrive deletion)
            if 'id' in metadata:
                keep_quality_with_path['cloud_id'] = metadata['id']
            
            updated_delete = []
            for del_temp_path, del_quality in group['delete']:
                metadata = photo_metadata.get(str(del_temp_path), {})
                cloud_del_path = metadata.get('path', str(del_temp_path))
                
                # Store temp path for image reading, but add cloud_path to quality dict
                del_quality_with_path = del_quality.copy()
                del_quality_with_path['cloud_path'] = cloud_del_path
                # Also support legacy 'dropbox_path' key for backward compatibility
                del_quality_with_path['dropbox_path'] = cloud_del_path
                
                # Store item ID if available (needed for OneDrive deletion)
                if 'id' in metadata:
                    del_quality_with_path['cloud_id'] = metadata['id']
                
                updated_delete.append((del_temp_path, del_quality_with_path))
            
            updated_groups.append({
                'keep': (keep_temp_path, keep_quality_with_path),
                'delete': updated_delete
            })
        
        
        return updated_groups

