document.addEventListener('DOMContentLoaded', function() {
    var textareas = document.querySelectorAll('.easymde-editor');
    
    textareas.forEach(function(textarea) {
        if (textarea && !textarea.nextSibling?.classList?.contains('EasyMDEContainer')) {
            new EasyMDE({
                element: textarea,
                spellChecker: false,
                autosave: {
                    enabled: true,
                    uniqueId: textarea.id || "easymde-" + Math.random(),
                    delay: 1000,
                },
                toolbar: [
                    "bold", "italic", "heading", "|",
                    "quote", "unordered-list", "ordered-list", "|",
                    "link", "image", "table", "code", "|",
                    "preview", "side-by-side", "fullscreen", "|",
                    "guide"
                ],
                placeholder: "✍️ Écrivez en Markdown...",
                status: ["autosave", "lines", "words", "cursor"],
                cursorHeight: "24px",
                renderingConfig: {
                    codeSyntaxHighlighting: true,
                },
            });
        }
    });
});