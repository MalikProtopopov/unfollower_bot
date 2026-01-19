"""XLSX file generation for check results."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils.dataframe import dataframe_to_rows

from app.config import get_settings
from app.services.instagram_scraper import InstagramUser
from app.utils.logger import logger

settings = get_settings()


def create_styled_workbook(
    target_username: str,
    followers: list[InstagramUser],
    following: list[InstagramUser],
    non_mutual: list[InstagramUser],
) -> Workbook:
    """Create a styled Excel workbook with analysis results.

    Args:
        target_username: Target Instagram username
        followers: List of followers
        following: List of following
        non_mutual: List of non-mutual users

    Returns:
        Styled openpyxl Workbook
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Non-Mutual Analysis"

    # Styles
    header_font = Font(bold=True, size=14, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    subheader_font = Font(bold=True, size=11)
    subheader_fill = PatternFill(start_color="D6DCE5", end_color="D6DCE5", fill_type="solid")
    yes_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    no_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # --- Header Section ---
    ws.merge_cells("A1:G1")
    ws["A1"] = f"Анализ взаимных подписок: @{target_username}"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center")

    # Metadata
    ws["A3"] = "Дата анализа:"
    ws["B3"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws["A4"] = "Всего подписчиков:"
    ws["B4"] = len(followers)
    ws["A5"] = "Всего подписок:"
    ws["B5"] = len(following)
    ws["A6"] = "Не взаимных:"
    ws["B6"] = len(non_mutual)
    ws["A7"] = "Процент взаимности:"

    mutual_count = len(following) - len(non_mutual)
    mutual_percent = (mutual_count / len(following) * 100) if following else 0
    ws["B7"] = f"{mutual_percent:.1f}%"

    for row in range(3, 8):
        ws[f"A{row}"].font = Font(bold=True)

    # --- Data Table ---
    table_start_row = 9

    # Table headers
    headers = ["#", "Username", "Имя", "Подписан на вас?", "Вы подписаны?", "Взаимно?", "Ссылка"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=table_start_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

    # Create followers and following sets for quick lookup
    follower_usernames = {f.username.lower() for f in followers}
    following_usernames = {f.username.lower() for f in following}

    # Combine all users for complete picture
    all_users = {}

    # Add following users
    for user in following:
        all_users[user.username.lower()] = {
            "username": user.username,
            "full_name": user.full_name or "",
            "user_follows": True,
            "follows_user": user.username.lower() in follower_usernames,
        }

    # Add followers not in following
    for user in followers:
        if user.username.lower() not in all_users:
            all_users[user.username.lower()] = {
                "username": user.username,
                "full_name": user.full_name or "",
                "user_follows": False,
                "follows_user": True,
            }

    # Sort: non-mutual first (user follows but not followed back)
    sorted_users = sorted(
        all_users.values(),
        key=lambda x: (
            x["follows_user"],  # Not followed back first
            -x["user_follows"],  # User follows first
            x["username"].lower(),
        ),
    )

    # Write data rows
    for idx, user_data in enumerate(sorted_users, 1):
        row = table_start_row + idx
        is_mutual = user_data["user_follows"] and user_data["follows_user"]

        # Row number
        cell = ws.cell(row=row, column=1, value=idx)
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

        # Username
        cell = ws.cell(row=row, column=2, value=user_data["username"])
        cell.border = border

        # Full name
        cell = ws.cell(row=row, column=3, value=user_data["full_name"])
        cell.border = border

        # Follows user (target follows this person)
        follows_user_text = "✓" if user_data["follows_user"] else "✗"
        cell = ws.cell(row=row, column=4, value=follows_user_text)
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
        cell.fill = yes_fill if user_data["follows_user"] else no_fill

        # User follows (this person follows target)
        user_follows_text = "✓" if user_data["user_follows"] else "✗"
        cell = ws.cell(row=row, column=5, value=user_follows_text)
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
        cell.fill = yes_fill if user_data["user_follows"] else no_fill

        # Mutual
        mutual_text = "✓" if is_mutual else "✗"
        cell = ws.cell(row=row, column=6, value=mutual_text)
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
        cell.fill = yes_fill if is_mutual else no_fill

        # Instagram link
        ig_url = f"https://instagram.com/{user_data['username']}"
        cell = ws.cell(row=row, column=7, value="Открыть")
        cell.hyperlink = ig_url
        cell.font = Font(color="0563C1", underline="single")
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

    # Adjust column widths
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 12

    # --- Non-Mutual Only Sheet ---
    ws_non_mutual = wb.create_sheet(title="Non-Mutual Only")

    # Header
    ws_non_mutual.merge_cells("A1:D1")
    ws_non_mutual["A1"] = f"Не взаимные подписки @{target_username}"
    ws_non_mutual["A1"].font = Font(bold=True, size=14)

    ws_non_mutual["A2"] = f"Вы подписаны на {len(non_mutual)} аккаунтов, которые не подписаны на вас"
    ws_non_mutual["A2"].font = Font(italic=True, color="666666")

    # Table headers
    nm_headers = ["#", "Username", "Имя", "Ссылка"]
    for col, header in enumerate(nm_headers, 1):
        cell = ws_non_mutual.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    # Data
    for idx, user in enumerate(non_mutual, 1):
        row = 4 + idx
        ws_non_mutual.cell(row=row, column=1, value=idx).border = border
        ws_non_mutual.cell(row=row, column=2, value=user.username).border = border
        ws_non_mutual.cell(row=row, column=3, value=user.full_name or "").border = border
        
        # Instagram link
        ig_url = f"https://instagram.com/{user.username}"
        cell = ws_non_mutual.cell(row=row, column=4, value="Открыть")
        cell.hyperlink = ig_url
        cell.font = Font(color="0563C1", underline="single")
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

    ws_non_mutual.column_dimensions["A"].width = 6
    ws_non_mutual.column_dimensions["B"].width = 25
    ws_non_mutual.column_dimensions["D"].width = 12
    ws_non_mutual.column_dimensions["C"].width = 30

    return wb


async def generate_xlsx_report(
    check_id: str,
    target_username: str,
    followers: list[InstagramUser],
    following: list[InstagramUser],
    non_mutual: list[InstagramUser],
) -> str:
    """Generate XLSX report file.

    Args:
        check_id: Check UUID
        target_username: Target username
        followers: List of followers
        following: List of following
        non_mutual: List of non-mutual users

    Returns:
        Path to generated file
    """
    # Ensure upload directory exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    filename = f"{check_id}.xlsx"
    file_path = upload_dir / filename

    # Create workbook
    wb = create_styled_workbook(target_username, followers, following, non_mutual)

    # Save file
    wb.save(file_path)

    logger.info(f"Generated XLSX report: {file_path}")

    return str(file_path)


async def generate_csv_report(
    check_id: str,
    target_username: str,
    non_mutual: list[InstagramUser],
) -> str:
    """Generate simple CSV report.

    Args:
        check_id: Check UUID
        target_username: Target username
        non_mutual: List of non-mutual users

    Returns:
        Path to generated file
    """
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{check_id}.csv"
    file_path = upload_dir / filename

    # Create DataFrame
    data = [
        {
            "#": idx,
            "Username": user.username,
            "Full Name": user.full_name or "",
        }
        for idx, user in enumerate(non_mutual, 1)
    ]

    df = pd.DataFrame(data)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")

    logger.info(f"Generated CSV report: {file_path}")

    return str(file_path)

