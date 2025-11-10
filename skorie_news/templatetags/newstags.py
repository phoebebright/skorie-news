from django import template
from django.template.loader import get_template
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag
def include_raw(path):
    """
    Includes the raw (unrendered) contents of a template file.

    Example:
        {% include_raw "partials/article_item.html" %}
    """
    template_obj = get_template(path)
    file_path = template_obj.origin.name
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    return mark_safe(content)
