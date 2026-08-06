/*
 * RDRF left-rail subsection navigation.
 *
 * Shared by CAP-06 (demographics rail) and CAP-07 (clinical form rail).
 * Usage: add `data-rdrf-subnav` to a <nav class="rdrf-subnav-rail"> whose
 * `.rdrf-subnav-rail__item` anchors point at same-page section ids.
 * Active state follows clicks and, where supported, scroll position.
 */
(function () {
    'use strict';

    function initSubnavRail(rail) {
        var links = Array.prototype.slice.call(
            rail.querySelectorAll('.rdrf-subnav-rail__item'));
        var sectionLinks = links.filter(function (link) {
            var href = link.getAttribute('href') || '';
            return href.charAt(0) === '#';
        });
        var sections = sectionLinks.map(function (link) {
            return document.getElementById(
                (link.getAttribute('href') || '').slice(1));
        }).filter(Boolean);

        function isVisible(section) {
            var card = section.closest('.rdrf-section-card, .card') || section;
            return !card.hidden && window.getComputedStyle(card).display !== 'none';
        }

        function syncVisibility() {
            var visibleLinks = [];
            sectionLinks.forEach(function (link) {
                var section = document.getElementById(
                    (link.getAttribute('href') || '').slice(1));
                var visible = section && isVisible(section);
                link.hidden = !visible;
                link.setAttribute('aria-hidden', visible ? 'false' : 'true');
                if (visible) { visibleLinks.push(link); }
            });

            var active = rail.querySelector('.rdrf-subnav-rail__item--active');
            if ((!active || active.hidden) && visibleLinks.length) {
                setActive(visibleLinks[0].getAttribute('href').slice(1));
            }
            rail.hidden = visibleLinks.length === 0;
        }

        function setActive(sectionId) {
            links.forEach(function (link) {
                var isActive = link.getAttribute('href') === '#' + sectionId;
                link.classList.toggle('rdrf-subnav-rail__item--active', isActive);
                if (isActive) {
                    link.setAttribute('aria-current', 'true');
                } else {
                    link.removeAttribute('aria-current');
                }
            });
        }

        function fixedHeaderOffset() {
            return Array.prototype.slice.call(
                document.querySelectorAll('.fixed-top, .banner')
            ).reduce(function (bottom, element) {
                return Math.max(bottom, element.getBoundingClientRect().bottom);
            }, 0) + 16;
        }

        function updateStickyOffset() {
            rail.style.setProperty(
                '--rdrf-sticky-offset', fixedHeaderOffset() + 'px'
            );
        }

        function scrollToSection(section) {
            var top = window.scrollY + section.getBoundingClientRect().top
                - fixedHeaderOffset();
            window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        }

        function expandAndScroll(section) {
            var card = section.closest('.card.collapsible');
            var body = card && card.querySelector(':scope > .card-body');

            if (!body || typeof window.jQuery === 'undefined') {
                scrollToSection(section);
                return;
            }

            var $body = window.jQuery(body);
            if ($body.hasClass('show')) {
                scrollToSection(section);
                return;
            }

            $body.one('shown.bs.collapse', function () {
                scrollToSection(section);
            });
            $body.collapse('show');
        }

        if (sectionLinks.length) { syncVisibility(); }
        updateStickyOffset();
        if (rail.dataset.rdrfStickyOffsetBound !== 'true') {
            window.addEventListener('resize', updateStickyOffset);
            rail.dataset.rdrfStickyOffsetBound = 'true';
        }

        sectionLinks.forEach(function (link) {
            link.addEventListener('click', function (event) {
                event.preventDefault();
                var sectionId = link.getAttribute('href').slice(1);
                var section = document.getElementById(sectionId);
                setActive(sectionId);
                window.history.pushState(null, '', '#' + sectionId);
                if (section) { expandAndScroll(section); }
            });
        });

        if ('IntersectionObserver' in window) {
            var visibility = {};
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    visibility[entry.target.id] = entry.isIntersecting;
                });
                var current = sections.filter(function (section) {
                    return visibility[section.id];
                })[0];
                if (current) { setActive(current.id); }
            }, { rootMargin: '-25% 0px -65% 0px' });
            sections.forEach(function (section) { observer.observe(section); });
        }

        var sectionObserver = new MutationObserver(syncVisibility);
        sections.forEach(function (section) {
            var card = section.closest('.rdrf-section-card, .card') || section;
            sectionObserver.observe(card, {
                attributes: true,
                attributeFilter: ['class', 'hidden', 'style']
            });
        });
    }

    function initializeNavigation() {
        Array.prototype.slice.call(
            document.querySelectorAll('[data-rdrf-module-nav]')
        ).forEach(function (nav) {
            if (nav.dataset.rdrfModuleNavReady === 'true') { return; }
            var source = document.querySelector('[data-rdrf-module-nav-source]');
            if (!source) { return; }

            Array.prototype.slice.call(
                source.querySelectorAll('a[href*="/forms/"]')
            ).forEach(function (link) {
                var item = link.cloneNode(true);
                item.className = 'rdrf-module-nav__item';
                if (link.classList.contains('selected-link')) {
                    item.classList.add('rdrf-module-nav__item--active');
                    item.setAttribute('aria-current', 'page');
                }
                nav.appendChild(item);
            });

            if (nav.children.length) {
                nav.dataset.rdrfModuleNavReady = 'true';
            }
        });

        Array.prototype.slice.call(
            document.querySelectorAll('[data-rdrf-subnav]')
        ).forEach(function (rail) {
            try {
                initSubnavRail(rail);
            } catch (error) {
                rail.dataset.rdrfSubnavError = 'true';
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeNavigation);
    } else {
        initializeNavigation();
    }
    window.addEventListener('load', initializeNavigation);
})();
