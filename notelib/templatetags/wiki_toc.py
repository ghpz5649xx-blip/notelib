from django import template
from django.utils.safestring import mark_safe
from bs4 import BeautifulSoup
import uuid

register = template.Library()

@register.simple_tag
def build_toc(content_html, max_depth=4):
    """
    Construit un sommaire hiérarchique en accordéon à partir des titres h2–h3.
    Les sections h2 sont rétractées par défaut et peuvent se déplier pour afficher les h3.
    Le chevron n'apparaît que si la section h2 contient des h3.
    """
    soup = BeautifulSoup(content_html, "html.parser")
    headings = []
    seen = set()

    # Récupère uniquement les <h2>, <h3>
    for h in soup.find_all(["h2", "h3"]):
        text = h.get_text(strip=True)
        
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        
        anchor = h.get("id")
        if not anchor:
            anchor = text.lower().replace(" ", "-").replace("'", "").replace("'", "")
            h["id"] = anchor
        
        level = int(h.name[1])
        if level <= max_depth:
            headings.append({"level": level, "text": text, "anchor": anchor})
    
    if not headings:
        return ""
    
    html = "<nav class='wiki-toc-accordion'>"
    
    i = 0
    while i < len(headings):
        h = headings[i]
        
        if h["level"] == 2:
            collapse_id = f"toc-collapse-{uuid.uuid4().hex[:8]}"
            
            # Collecte les h3 qui suivent ce h2
            sub_items = []
            j = i + 1
            while j < len(headings) and headings[j]["level"] == 3:
                sub_items.append(headings[j])
                j += 1
            
            # Titre h2 avec chevron seulement si des h3 existent
            html += "<div class='toc-item toc-h2-item'>"
            
            if sub_items:
                html += f"""
                <div class='toc-header'>
                    <button class='toc-toggle' 
                            type='button' 
                            data-toggle='collapse' 
                            data-target='#{collapse_id}' 
                            aria-expanded='false' 
                            aria-controls='{collapse_id}'>
                        <span class='toc-chevron'>›</span>
                    </button>
                    <a href='#{h['anchor']}' class='toc-link toc-h2-link'>{h['text']}</a>
                </div>
                <div class='collapse toc-h3-container' id='{collapse_id}'>
                """
                for sub in sub_items:
                    html += f"<a href='#{sub['anchor']}' class='toc-link toc-h3-link'>{sub['text']}</a>"
                html += "</div>"
            else:
                html += f"<div class='toc-header'><a href='#{h['anchor']}' class='toc-link toc-h2-link'>{h['text']}</a></div>"
            
            html += "</div>"
            i = j
        else:
            # h3 orphelin
            html += f"<div class='toc-item'><a href='#{h['anchor']}' class='toc-link toc-h3-link'>{h['text']}</a></div>"
            i += 1
    
    html += "</nav>"
    
    return mark_safe(html)