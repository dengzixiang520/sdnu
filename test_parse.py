import pdfplumber
import json

pdf_path = 'D:/install/edge/邓子祥(2026-2027-1)课表 (1).pdf'

# 节次时间映射
slot_times = {
    '1': ('08:20', '09:55'),
    '3': ('10:10', '11:45'),
    '5': ('14:00', '15:35'),
    '7': ('15:50', '17:25'),
    '9': ('19:00', '20:35')
}

# 星期映射（列索引 -> 星期几）
day_map = {
    2: '周一', 3: '周二', 4: '周三', 5: '周四', 6: '周五', 7: '周六', 8: '周日'
}

events = []

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    
    for table in tables:
        for row_idx, row in enumerate(table):
            if not row or len(row) < 3:
                continue
            
            # 获取节次信息
            slot = str(row[1]).strip() if row[1] else ''
            if slot not in slot_times:
                continue
            
            start_time, end_time = slot_times[slot]
            
            # 遍历星期列
            for col_idx in range(2, min(len(row), 9)):
                cell = row[col_idx]
                if cell and len(str(cell).strip()) > 10:
                    cell_text = str(cell)
                    
                    # 提取课程名称
                    title = ''
                    if '★' in cell_text:
                        title = cell_text.split('★')[0].strip()
                    else:
                        lines = cell_text.split('\n')
                        title = lines[0].strip()[:20]
                    
                    # 提取教师
                    teacher = ''
                    if '教师:' in cell_text:
                        teacher_part = cell_text.split('教师:')[1]
                        if '/' in teacher_part:
                            teacher = teacher_part.split('/')[0].strip()
                        else:
                            teacher = teacher_part.split('\n')[0].strip()
                    
                    # 提取地点
                    location = ''
                    if '场地:' in cell_text:
                        location_part = cell_text.split('场地:')[1]
                        if '/' in location_part:
                            location = location_part.split('/')[0].strip()
                        else:
                            location = location_part.split('\n')[0].strip()
                    
                    day = day_map.get(col_idx, '周一')
                    
                    events.append({
                        'title': title,
                        'starts_at': f'2026-09-01T{start_time}:00',
                        'ends_at': f'2026-09-01T{end_time}:00',
                        'location': location,
                        'day_of_week': day,
                        'teacher': teacher
                    })

print(f'解析课程数: {len(events)}')
print()
print('解析结果：')
for event in sorted(events, key=lambda x: (x['day_of_week'], x['starts_at'])):
    day = event['day_of_week']
    title = event['title']
    start = event['starts_at'][11:16]
    end = event['ends_at'][11:16]
    location = event['location']
    teacher = event['teacher']
    print(f'{day} | {title} | {start}-{end} | {location} | {teacher}')