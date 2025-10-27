import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import NotebookMeta, NotebookExecution
from .forms import NotebookUploadForm
from .services import notebook_service

logger = logging.getLogger("notelib")


@login_required
def notebook_list(request):
    """Liste tous les notebooks uploadés."""
    notebooks = NotebookMeta.objects.select_related('uploaded_by', 'wiki_article').all()
    
    context = {
        'notebooks': notebooks,
        'stats': {
            'total': notebooks.count(),
            'pending': notebooks.filter(status='pending').count(),
            'processing': notebooks.filter(status='processing').count(),
            'success': notebooks.filter(status='success').count(),
            'error': notebooks.filter(status='error').count(),
        }
    }
    
    return render(request, 'notebooks/list.html', context)


@login_required
def notebook_upload(request):
    """Formulaire d'upload de notebook."""
    if request.method == 'POST':
        form = NotebookUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            notebook = form.save(commit=False)
            notebook.uploaded_by = request.user
            
            # Calcul du hash
            notebook.file.open()
            notebook.hash = notebook_service.compute_hash(notebook.file.file)
            notebook.size = notebook.file.size
            notebook.file.close()
            
            # Vérification si le notebook existe déjà
            existing = NotebookMeta.objects.filter(hash=notebook.hash).first()
            if existing:
                messages.warning(
                    request,
                    f"Ce notebook existe déjà : {existing.name}"
                )
                return redirect('notebooks:detail', pk=existing.pk)
            
            notebook.save()
            
            # Traitement asynchrone (ou synchrone pour MVP)
            try:
                sandbox_mode = form.cleaned_data.get('sandbox_mode', 'temp')
                create_wiki = form.cleaned_data.get('create_wiki_article', False)
                
                execution = notebook_service.process_notebook(
                    notebook,
                    sandbox_mode=sandbox_mode,
                    create_wiki_article=create_wiki
                )
                
                messages.success(
                    request,
                    f"Notebook traité avec succès : "
                    f"{execution.features_imported} features importées"
                )
                
            except Exception as e:
                messages.error(
                    request,
                    f"Erreur lors du traitement : {str(e)}"
                )
            
            return redirect('notebooks:detail', pk=notebook.pk)
    
    else:
        form = NotebookUploadForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'notebooks/upload.html', context)


@login_required
def notebook_detail(request, pk):
    """Détails d'un notebook et de ses features."""
    notebook = get_object_or_404(
        NotebookMeta.objects.select_related('uploaded_by', 'wiki_article')
                            .prefetch_related('features__feature', 'executions'),
        pk=pk
    )
    
    context = {
        'notebook': notebook,
        'features': notebook.features.all(),
        'executions': notebook.executions.all()[:10],  # 10 dernières exécutions
    }
    
    return render(request, 'notebooks/detail.html', context)


@login_required
@require_http_methods(["POST"])
def notebook_reprocess(request, pk):
    """Retraite un notebook existant."""
    notebook = get_object_or_404(NotebookMeta, pk=pk)
    
    try:
        sandbox_mode = request.POST.get('sandbox_mode', 'temp')
        
        execution = notebook_service.process_notebook(
            notebook,
            sandbox_mode=sandbox_mode,
            create_wiki_article=False
        )
        
        return JsonResponse({
            'status': 'success',
            'features_imported': execution.features_imported,
            'features_existing': execution.features_existing,
            'errors_count': execution.errors_count,
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def notebook_delete(request, pk):
    """Supprime un notebook."""
    notebook = get_object_or_404(NotebookMeta, pk=pk)
    
    # Vérification des permissions
    if notebook.uploaded_by != request.user and not request.user.is_staff:
        return JsonResponse({
            'status': 'error',
            'error': 'Permission denied'
        }, status=403)
    
    try:
        # Suppression du fichier
        notebook.file.delete()
        notebook.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Notebook {notebook.name} supprimé'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)