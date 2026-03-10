import glob

files = glob.glob('templates/faculty_*.html')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Replace href="#" for Results & Analytics
    target = '<a href="#" class="nav-link">\n        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>\n        Results & Analytics\n      </a>'
    
    new_str = '<a href="{{ url_for(\'faculty_bp.faculty_results\') }}" class="nav-link">\n        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>\n        Results & Analytics\n      </a>'

    if target in content:
        content = content.replace(target, new_str)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f'Updated {f}')
