import csv
import json


def get_country_timezones():
    country_timezones = {}
    countries = {}
    timezones = []
    with open("./tools/country_timezones.csv", mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            country = row['Code']
            timezone = row['Timezone']
            timezones.append(timezone)
            if country not in country_timezones:
                country_timezones[country] = []
            country_timezones[country].append(timezone)

            if country not in countries:
                countries[country] = row['Country']

    # sort countries by name
    countries = dict(sorted(countries.items(), key=lambda item: item[1]))

    return country_timezones, countries, timezones

def filename_to_bootstrap_icon(filename):
    # Dictionary mapping file extensions to Bootstrap 5 icon class names
    extension_to_icon = {
        'pdf': 'bi-filetype-pdf',
        'doc': 'bi-filetype-doc',
        'docx': 'bi-filetype-docx',
        # 'xls': 'bi-filetype-xls',
        # 'xlsx': 'bi-filetype-xlsx',
        # 'ppt': 'bi-filetype-ppt',
        # 'pptx': 'bi-filetype-pptx',
        # 'jpg': 'bi-filetype-jpg',
        # 'jpeg': 'bi-filetype-jpg',
        # 'png': 'bi-filetype-png',
        # 'gif': 'bi-filetype-gif',
        # 'svg': 'bi-filetype-svg',
        # 'mp3': 'bi-filetype-mp3',
        # 'mp4': 'bi-filetype-mp4',
        # 'zip': 'bi-filetype-zip',
        # 'rar': 'bi-filetype-zip',
        'txt': 'bi-filetype-txt',
        # 'html': 'bi-filetype-html',
        # 'css': 'bi-filetype-css',
        # 'js': 'bi-filetype-js',
        # 'json': 'bi-filetype-json',
        # 'xml': 'bi-filetype-xml',
        # 'csv': 'bi-filetype-csv',
        # 'php': 'bi-filetype-php',
        # 'py': 'bi-filetype-py',
        # 'c': 'bi-filetype-c',
        # 'cpp': 'bi-filetype-cpp',
        # 'exe': 'bi-filetype-exe',

    }

    # Check if the filename contains an extension
    if '.' in filename:
        # Extract the file extension
        extension = filename.rsplit('.', 1)[1].lower()
    else:
        extension = ''

    # Get the corresponding icon class or use a default icon
    icon_class = extension_to_icon.get(extension, 'bi-file-earmark')

    # Construct the HTML code for the icon
    html_code = f'<i class="bi {icon_class}"></i>'

    return html_code


def clean_for_json(data):
    """
    Recursively remove any keys from a dictionary (or elements from a list)
    that are not JSON serializable.
    """
    if isinstance(data, dict):
        cleaned_dict = {}
        for k, v in data.items():
            try:
                # Test if this specific value is serializable
                json.dumps(v)
                # If it's a dict or list, we still need to recurse to clean nested items
                if isinstance(v, (dict, list)):
                    cleaned_dict[k] = clean_for_json(v)
                else:
                    cleaned_dict[k] = v
            except (TypeError, OverflowError):
                # Not serializable (e.g., a User object, a datetime object, etc.)
                continue
        return cleaned_dict
    elif isinstance(data, list):
        cleaned_list = []
        for item in data:
            try:
                json.dumps(item)
                if isinstance(item, (dict, list)):
                    cleaned_list.append(clean_for_json(item))
                else:
                    cleaned_list.append(item)
            except (TypeError, OverflowError):
                continue
        return cleaned_list
    return data
