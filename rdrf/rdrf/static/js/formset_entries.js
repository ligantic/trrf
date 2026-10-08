/*
 * Shared behaviour for repeatable (formset) entries.
 *
 * Markup contract (see rdrf_cdes/formset_entry_actions.html and
 * rdrf_cdes/formset_add_button.html):
 *   .rdrf-multisection-entry            one entry in a formset
 *   .rdrf-multisection-entry__fields    the entry's input rows
 *   .rdrf-multisection-entry__toolbar   holds the Remove button
 *   .rdrf-multisection-entry__removed   holds the Undo block
 *   [data-rdrf-formset-remove]          Remove button
 *   [data-rdrf-formset-undo]            Undo button
 *   [data-rdrf-formset-delete]          wrapper of the hidden DELETE checkbox
 *   [data-rdrf-formset-add]             Add button (gets a tooltip)
 *
 * Remove ticks the entry's DELETE checkbox and hides its fields. Undo clears
 * the checkbox and restores the fields. The server applies the deletion on save.
 */
(function () {
    "use strict";

    var ENTRY_CLASS = "rdrf-multisection-entry";
    var FIELDS_CLASS = "rdrf-multisection-entry__fields";
    var TOOLBAR_CLASS = "rdrf-multisection-entry__toolbar";
    var REMOVED_CLASS = "rdrf-multisection-entry__removed";

    function directChild(entry, className) {
        for (var i = 0; i < entry.children.length; i++) {
            if (entry.children[i].classList.contains(className)) {
                return entry.children[i];
            }
        }
        return null;
    }

    function deleteCheckboxes(entry) {
        return entry.querySelectorAll("[data-rdrf-formset-delete] input[type='checkbox']");
    }

    function setRemoved(entry, removed) {
        var fields = directChild(entry, FIELDS_CLASS);
        var toolbar = directChild(entry, TOOLBAR_CLASS);
        var removedBlock = directChild(entry, REMOVED_CLASS);

        if (fields) {
            fields.hidden = removed;
        }
        if (toolbar) {
            toolbar.hidden = removed;
        }
        if (removedBlock) {
            removedBlock.hidden = !removed;
        }

        deleteCheckboxes(entry).forEach(function (box) {
            box.checked = removed;
        });
        entry.classList.toggle("is-removed", removed);
    }

    function focusFirst(entry, selector) {
        var target = entry.querySelector(selector);
        if (target) {
            target.focus();
        }
    }

    function initEntries() {
        document.querySelectorAll("." + ENTRY_CLASS).forEach(function (entry) {
            var checked = Array.prototype.some.call(deleteCheckboxes(entry), function (box) {
                return box.checked;
            });
            if (checked) {
                setRemoved(entry, true);
            }
        });
    }

    function initTooltips() {
        if (!window.bootstrap || !window.bootstrap.Tooltip) {
            return;
        }
        document.querySelectorAll("[data-rdrf-formset-add][data-bs-toggle='tooltip']").forEach(function (el) {
            window.bootstrap.Tooltip.getOrCreateInstance(el);
        });
    }

    // Delegated handlers so entries added later (cloned from the empty template) work too.
    document.addEventListener("click", function (event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }

        var removeButton = target.closest("[data-rdrf-formset-remove]");
        if (removeButton) {
            event.preventDefault();
            var entryToRemove = removeButton.closest("." + ENTRY_CLASS);
            if (entryToRemove) {
                setRemoved(entryToRemove, true);
                focusFirst(entryToRemove, "[data-rdrf-formset-undo]");
            }
            return;
        }

        var undoButton = target.closest("[data-rdrf-formset-undo]");
        if (undoButton) {
            event.preventDefault();
            var entryToRestore = undoButton.closest("." + ENTRY_CLASS);
            if (entryToRestore) {
                setRemoved(entryToRestore, false);
                focusFirst(entryToRestore, "[data-rdrf-formset-remove]");
            }
        }
    });

    function onReady() {
        initEntries();
        initTooltips();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", onReady);
    } else {
        onReady();
    }
})();
