document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('.toastui-editor');

    textareas.forEach(function(textarea) {
        if (!textarea.nextElementSibling?.classList?.contains('toastui-editor-defaultUI')) {
            // Crée un conteneur juste avant le textarea
            const container = document.createElement('div');
            textarea.parentNode.insertBefore(container, textarea);
            textarea.style.display = 'none';

            const editor = new toastui.Editor({
                el: container,
                height: '600px',
                initialEditType: 'wysiwyg',
                previewStyle: 'vertical',
                initialValue: textarea.value || '',
                placeholder: '✍️ Écrivez...',
                usageStatistics: false,
                hideModeSwitch: false,
            });

            // Synchroniser le contenu Markdown dans le textarea avant submit
            if (textarea.form) {
                textarea.form.addEventListener('submit', function() {
                    textarea.value = editor.getMarkdown();
                });
            }
        }
    });
});
