// Load sidebar into every page
function loadSidebar() {
  (async () => {
    try {
      // Fetch sidebar HTML
      const response = await fetch('/sidebar.html');
      const sidebarHTML = await response.text();

      // Create container if it doesn't exist
      let container = document.getElementById('sidebar-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'sidebar-container';
        document.body.insertAdjacentElement('afterbegin', container);
      }

      // Insert sidebar
      container.innerHTML = sidebarHTML;

      // Initialize sidebar functionality
      initSidebar();
    } catch (error) {
      console.error('Failed to load sidebar:', error);
    }
  })();
}

// Run immediately if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadSidebar);
} else {
  loadSidebar();
}

function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const collapseBtn = document.getElementById('collapse-btn');
  const body = document.body;

  // Load collapse state from localStorage
  const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
  if (isCollapsed) {
    sidebar.classList.add('collapsed');
    body.classList.add('sidebar-collapsed');
    body.classList.remove('sidebar-open');
  } else {
    sidebar.classList.remove('collapsed');
    body.classList.add('sidebar-open');
    body.classList.remove('sidebar-collapsed');
  }

  // Toggle collapse on button click
  collapseBtn.addEventListener('click', () => {
    const collapsed = sidebar.classList.toggle('collapsed');
    localStorage.setItem('sidebar-collapsed', collapsed);

    if (collapsed) {
      body.classList.add('sidebar-collapsed');
      body.classList.remove('sidebar-open');
    } else {
      body.classList.add('sidebar-open');
      body.classList.remove('sidebar-collapsed');
    }
  });

  // Set active link based on current page
  const currentPage = getCurrentPageName();
  const links = document.querySelectorAll('.sidebar-nav a');
  links.forEach(link => {
    const pageName = link.getAttribute('data-page');
    if (pageName === currentPage) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });
}

function getCurrentPageName() {
  // Get the current page name from the URL
  const pathname = window.location.pathname;
  const filename = pathname.substring(pathname.lastIndexOf('/') + 1);
  const pageName = filename.replace('.html', '');

  // Map filenames to page names
  const pageMap = {
    'dashboard': 'dashboard',
    'containers': 'containers',
    'tabulator': 'tabulator',
    'tabulator2': 'tabulator',
    'tabulator-option-b': 'tabulator',
    'ai': 'ai',
    'calendar': 'calendar',
    'dispatch.backup': 'containers',
    'index': 'dashboard',
    '': 'dashboard'
  };

  return pageMap[pageName] || pageName;
}
