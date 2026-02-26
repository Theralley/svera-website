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
})();
