/* SVERA — main.js */
(function() {
  'use strict';

  // Mobile hamburger toggle
  var hamburger = document.querySelector('.hamburger');
  var nav = document.querySelector('.main-nav');

  if (hamburger && nav) {
    hamburger.addEventListener('click', function() {
      hamburger.classList.toggle('active');
      nav.classList.toggle('open');
    });
  }

  // Mobile dropdown toggle — first tap opens dropdown, second navigates
  var navItems = document.querySelectorAll('.nav-list > li');
  navItems.forEach(function(item) {
    var link = item.querySelector('a');
    var dropdown = item.querySelector('.dropdown');
    if (dropdown && link) {
      link.addEventListener('click', function(e) {
        if (window.innerWidth <= 768) {
          if (!item.classList.contains('open')) {
            e.preventDefault();
            // Close other open dropdowns
            navItems.forEach(function(other) {
              if (other !== item) other.classList.remove('open');
            });
            item.classList.add('open');
          }
          // If already open, allow normal navigation
        }
      });
    }
  });

  // Close nav on resize to desktop
  window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
      if (nav) nav.classList.remove('open');
      if (hamburger) hamburger.classList.remove('active');
      navItems.forEach(function(item) {
        item.classList.remove('open');
      });
    }
  });

  // Close mobile nav when clicking outside
  document.addEventListener('click', function(e) {
    if (window.innerWidth <= 768 && nav && hamburger) {
      if (!nav.contains(e.target) && !hamburger.contains(e.target)) {
        nav.classList.remove('open');
        hamburger.classList.remove('active');
        navItems.forEach(function(item) {
          item.classList.remove('open');
        });
      }
    }
  });

  // Progressive "Show More" for news cards
  var VISIBLE_STEP = 3;
  var cards = document.querySelectorAll('.news-list > .news-card');
  var btn = document.getElementById('show-more-news');
  var wrap = btn ? btn.parentElement : null;

  if (cards.length && btn) {
    // Hide cards beyond initial batch
    for (var i = VISIBLE_STEP; i < cards.length; i++) {
      cards[i].style.display = 'none';
    }
    // Hide button if all cards already visible
    if (cards.length <= VISIBLE_STEP) {
      wrap.style.display = 'none';
    }
    btn.addEventListener('click', function() {
      var shown = 0;
      for (var j = 0; j < cards.length; j++) {
        if (cards[j].style.display === 'none') {
          cards[j].style.display = '';
          shown++;
          if (shown >= VISIBLE_STEP) break;
        }
      }
      // Check if any remain hidden
      var anyHidden = false;
      for (var k = 0; k < cards.length; k++) {
        if (cards[k].style.display === 'none') { anyHidden = true; break; }
      }
      if (!anyHidden) wrap.style.display = 'none';
    });
  }
})();
