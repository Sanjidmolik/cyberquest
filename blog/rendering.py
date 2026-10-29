"""Markdown to safe HTML.

1. Python-Markdown with raw HTML switched off: HTML typed into a post is shown as text,
   never interpreted.
2. nh3 (Rust "ammonia") with an explicit allow-list: no scripts, styles, iframes, forms or
   event handlers; links only http(s)/mailto with rel="nofollow noopener noreferrer";
   images only from this blog's own image URLs. Run on save and again when shown.
"""

import markdown
import nh3
from django.utils.safestring import mark_safe

IMAGE_PREFIX = "/blog/img/"
TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "strong", "em", "del", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "img", "table", "thead", "tbody", "tr", "th", "td",
}
ATTRIBUTES = {"a": {"href", "title"}, "img": {"src", "alt", "title"}, "th": {"align"}, "td": {"align"}}
SCHEMES = {"http", "https", "mailto"}


class NoRawHtml(markdown.Extension):
    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")


def _attribute_filter(tag, attribute, value):
    if tag == "img" and attribute == "src" and not value.startswith(IMAGE_PREFIX):
        return None                     # no outside images (tracking pixels, mixed content)
    return value


def sanitise(html):
    return nh3.clean(html, tags=TAGS, attributes=ATTRIBUTES, url_schemes=SCHEMES,
                     link_rel="nofollow noopener noreferrer", attribute_filter=_attribute_filter,
                     strip_comments=True)


def render(body):
    """Markdown source -> sanitised HTML. A post's own title is its only <h1>, so # becomes <h2>."""
    html = markdown.markdown(body or "", extensions=["tables", "fenced_code", "sane_lists", NoRawHtml()],
                             output_format="html")
    html = html.replace("<h1>", "<h2>").replace("</h1>", "</h2>")
    return sanitise(html)


def safe_html(stored):
    """Sanitise stored HTML again on the way out, then mark it safe for the template."""
    return mark_safe(sanitise(stored or ""))   # noqa: S308 - output of the allow-list sanitiser
