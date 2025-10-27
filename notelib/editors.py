from wiki.editors.base import BaseEditor
from django.templatetags.static import static

class EasyMDEEditor(BaseEditor):
    """Éditeur EasyMDE pour django-wiki"""
    
    editor_id = 'easymde'
    
    class Media:
        css = {
            'all': (
                'easymde/css/easymde.min.css',
            )
        }
        js = (
            'easymde/js/easymde.min.js',
            'js/easymde-init.js',
        )
    
    def get_admin_widget(self, instance=None):
        from django import forms
        attrs = {'class': 'easymde-editor'}
        # Ne pas pré-remplir si c'est une nouvelle page
        print(f'instance : {instance}')
        if instance is None:
            attrs['placeholder'] = 'Commencez à écrire...'
        return forms.Textarea(attrs=attrs)
    
    def get_widget(self, instance=None):
        from django import forms
        attrs = {'class': 'easymde-editor'}
        # Ne pas pré-remplir si c'est une nouvelle page
        if instance is None:
            attrs['placeholder'] = 'Commencez à écrire...'
        return forms.Textarea(attrs=attrs)
    
from wiki.editors.base import BaseEditor

class ToastUIEditor(BaseEditor):
    """Éditeur Toast UI pour django-wiki"""
    
    editor_id = 'toastui'
    
    class Media:
        css = {
            'all': (
                'toastui/css/toastui-editor.min.css',
            )
        }
        js = (
            'toastui/js/toastui-editor-all.min.js',
            'js/toastui-init.js',  # Ton script d'init custom
        )
    
    def get_admin_widget(self, instance=None):
        from django import forms
        attrs = {'class': 'toastui-editor'}
        if instance is None:
            attrs['placeholder'] = 'Commencez à écrire...'
        return forms.Textarea(attrs=attrs)
    
    def get_widget(self, instance=None):
        from django import forms
        attrs = {'class': 'toastui-editor'}
        if instance is None:
            attrs['placeholder'] = 'Commencez à écrire...'
        return forms.Textarea(attrs=attrs)
