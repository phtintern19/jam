// rbac-router.js
// Handles Role-Based Access Control and Dynamic Sidebar rendering

document.addEventListener('DOMContentLoaded', () => {
    initRBAC();
});


// Remove the loading shield smoothly once RBAC is ready
function removeShield() {
    const shield = document.getElementById('rbac-shield');
    if (!shield) return;
    shield.classList.add('hidden');
    setTimeout(() => shield.remove(), 300);
}

function initRBAC() {
    const userStr = sessionStorage.getItem('user');
    let path = window.location.pathname + window.location.hash;

    if (!userStr) {
        if (window.location.pathname !== '/' && window.location.pathname !== '/index.html') {
            window.location.replace('/index.html');
        }
        removeShield();
        return;
    }
    
    let user;
    try {
        user = JSON.parse(userStr);
    } catch(e) {
        if (path !== '/' && path !== '/index.html') {
            window.location.replace('/index.html');
        }
        removeShield();
        return;
    }

    // Role can be in user.role or user.user_type
    const role = user.role || user.user_type; 

    // Normalize direct HTML access
    if (path.includes('team-owner-dashboard.html')) {
        const currentHash = window.location.hash;
        if (role === 'team_manager') {
            window.history.replaceState({}, '', '/dashboard/manager' + currentHash);
            path = '/dashboard/manager' + currentHash;
        } else if (role === 'team_analyst') {
            window.history.replaceState({}, '', '/dashboard/analyst' + currentHash);
            path = '/dashboard/analyst' + currentHash;
        } else {
            window.history.replaceState({}, '', '/dashboard' + currentHash);
            path = '/dashboard' + currentHash;
        }
    }

    // 1. Route Protection Logic
    if (path.startsWith('/dashboard/manager') && role !== 'team_manager' && role !== 'team_owner') {
        renderAccessDenied("Managers and Owners only");
        return;
    }
    if (path.startsWith('/dashboard/analyst') && role !== 'team_analyst' && role !== 'team_owner') {
        renderAccessDenied("Analysts and Owners only");
        return;
    }
    if (path === '/dashboard' && role !== 'team_owner') {
        // Auto-redirect if they try to access the base dashboard without Owner rights
        if (role === 'team_manager') {
            window.history.replaceState({}, '', '/dashboard/manager');
            path = '/dashboard/manager';
        } else if (role === 'team_analyst') {
            window.history.replaceState({}, '', '/dashboard/analyst');
            path = '/dashboard/analyst';
        } else {
            renderAccessDenied("Owners only");
            return;
        }
    }

    // 2. Render Sidebar
    renderSidebar(role, path);

    // 3. Render Panels
    renderPanels(role, path);

    // 4. Remove the loading shield now that the correct content is shown
    removeShield();

    // Handle Browser Back/Forward navigation
    window.addEventListener('popstate', () => {
        const newPath = window.location.pathname + window.location.hash;
        renderSidebar(role, newPath);
        renderPanels(role, newPath);
    });
}

function renderPanels(role, path) {
    // Hide all panels first
    document.querySelectorAll('.role-panel').forEach(p => p.style.display = 'none');

    if (path.startsWith('/dashboard/manager') || (role === 'team_manager' && path.includes('dashboard'))) {
        let p = document.getElementById('manager-panel');
        if (p) p.style.display = 'grid';
        let ownerP = document.getElementById('owner-panel');
        if (ownerP) ownerP.style.display = 'grid';
    } else if (path.startsWith('/dashboard/analyst') || (role === 'team_analyst' && path.includes('dashboard'))) {
        let p = document.getElementById('analyst-panel');
        if (p) p.style.display = 'grid';
        let ownerP = document.getElementById('owner-panel');
        if (ownerP) ownerP.style.display = 'grid';
    } else {
        let p = document.getElementById('owner-panel');
        if (p) p.style.display = 'grid';
    }
}

function renderAccessDenied(msg) {
    removeShield();
    const dashboard = document.querySelector('.saas-dashboard');
    if (dashboard) {
        dashboard.innerHTML = `
            <div class="glass-card" style="text-align: center; color: white; padding: 5rem 2rem; margin: auto; max-width: 500px;">
                <i class="fas fa-lock" style="font-size: 4rem; color: #ef4444; margin-bottom: 1rem;"></i>
                <h2>Access Denied</h2>
                <p style="color: var(--text-muted); margin-top: 0.5rem;">${msg}</p>
                <button class="btn-outline-premium" style="margin-top: 2rem;" onclick="logout()">Back to Login</button>
            </div>
        `;
    }
}

function renderSidebar(role, currentPath) {
    const sidebar = document.getElementById('unified-sidebar');
    if (!sidebar) return;

    let items = [];
    if (role === 'team_owner') {
        items = [
            { title: 'Dashboard', icon: 'fa-tachometer-alt', path: '/dashboard' },
            { title: 'Players / Squad', icon: 'fa-users', path: '/dashboard#players' },
            { title: 'Auction', icon: 'fa-gavel', path: '/dashboard#auction' },
            { title: 'Wallet', icon: 'fa-wallet', path: '/dashboard#wallet' },
            { title: 'Reports', icon: 'fa-file-alt', path: '/dashboard#reports' },
            { title: 'Team Manager Panel', icon: 'fa-user-tie', path: '/dashboard/manager' },
            { title: 'Analyst Panel', icon: 'fa-chart-pie', path: '/dashboard/analyst' },
            { title: 'Settings', icon: 'fa-cog', path: '/dashboard#settings' }
        ];
    } else if (role === 'team_manager') {
        items = [
            { title: 'Dashboard', icon: 'fa-tachometer-alt', path: '/dashboard/manager' },
            { title: 'Players / Squad', icon: 'fa-users', path: '/dashboard/manager#players' },
            { title: 'Auction', icon: 'fa-gavel', path: '/dashboard/manager#auction' },
            { title: 'Wallet', icon: 'fa-wallet', path: '/dashboard/manager#wallet' },
            { title: 'Reports', icon: 'fa-file-alt', path: '/dashboard/manager#reports' },
            { title: 'Settings', icon: 'fa-cog', path: '/dashboard/manager#settings' }
        ];
    } else if (role === 'team_analyst') {
        items = [
            { title: 'Dashboard', icon: 'fa-tachometer-alt', path: '/dashboard/analyst' },
            { title: 'Analytics', icon: 'fa-chart-pie', path: '/dashboard/analyst#analytics' },
            { title: 'Performance', icon: 'fa-fire', path: '/dashboard/analyst#performance' },
            { title: 'Scout Pool', icon: 'fa-users', path: '/dashboard/analyst#reports' },
            { title: 'Predictions', icon: 'fa-brain', path: '/dashboard/analyst#predictions' },
            { title: 'Settings', icon: 'fa-cog', path: '/dashboard/analyst#settings' }
        ];
    }

    let html = '<div style="flex: 1; overflow-y: auto;">';
    items.forEach(item => {
        const isActive = (item.path && item.path === currentPath) ? 'active' : '';
        if (item.path) {
            html += `<a href="${item.path}" class="sidebar-item ${isActive} rbac-link" data-path="${item.path}"><i class="fas ${item.icon}"></i> <span>${item.title}</span></a>`;
        } else {
            // Placeholder for generic links
            html += `<a href="#" class="sidebar-item" onclick="return false;"><i class="fas ${item.icon}"></i> <span>${item.title}</span></a>`;
        }
    });
    html += '</div>';
    
    html += `
    <div class="sidebar-footer" style="margin-top: auto; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.05);">
        <a href="#" class="sidebar-item" onclick="logout(); return false;" style="color: #ef4444;">
            <i class="fas fa-sign-out-alt"></i> <span>Logout</span>
        </a>
    </div>
    `;

    sidebar.style.display = 'flex';
    sidebar.style.flexDirection = 'column';
    sidebar.style.justifyContent = 'space-between';
    sidebar.style.overflowY = 'hidden';
    sidebar.innerHTML = html;

    // Attach SPA routing listeners
    document.querySelectorAll('.rbac-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const newPath = e.currentTarget.getAttribute('data-path');
            window.history.pushState({}, '', newPath);
            renderSidebar(role, newPath);
            renderPanels(role, newPath);
            
            // Dispatch a custom event to notify scripts (like team-owner-dashboard.js) of the view change
            window.dispatchEvent(new CustomEvent('viewChanged', { detail: { path: newPath } }));
        });
    });
}
