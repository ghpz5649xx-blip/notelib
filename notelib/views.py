from django.http import JsonResponse
from django.urls import reverse
from wiki.models import Article, ArticleRevision, URLPath


def article_tree_api(request):
    """
    Retourne l'arborescence des articles en JSON
    """
    def build_tree(urlpath, depth=0, max_depth=10):
        """Construit récursivement l'arborescence du wiki à partir d'un URLPath"""
        if depth > max_depth:
            return None

        article = urlpath.article
        current_revision = article.current_revision

        node = {
            'id': article.id,
            'title': current_revision.title if current_revision else 'Sans titre',
            'url': reverse('wiki:get', kwargs={'path': urlpath.path}),
            'children': []
        }

        # Récupérer les enfants du nœud courant (via URLPath, pas Article)
        children = URLPath.objects.filter(parent=urlpath)

        for child in children:
            child_node = build_tree(child, depth + 1, max_depth)
            if child_node:
                node['children'].append(child_node)

        return node
    
    try:
        # Récupérer l'article racine
        root_article = URLPath.objects.filter(parent__isnull=True).first()
        tree = build_tree(root_article)
        
        # Si on veut seulement les enfants de la racine
        return JsonResponse(tree['children'], safe=False)
        
    except Article.DoesNotExist:
        return JsonResponse([], safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)