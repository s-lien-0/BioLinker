/**
 * BioLinker — Frontend Application
 */

const API_BASE = 'http://localhost:8000';

// Auth state
let authToken = localStorage.getItem('biolinker_token');
let currentUser = null;
let isLoginMode = true;

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initTabs();
    initNetworkToggle();
    checkAPIHealth();
    checkAuth();
    loadDashboard();
});

// === Authentication ===
async function checkAuth() {
    if (!authToken) {
        updateAuthUI(null);
        return;
    }
    
    try {
        const user = await apiCall('/auth/me', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        currentUser = user;
        updateAuthUI(user);
    } catch (e) {
        // Token invalid or expired
        localStorage.removeItem('biolinker_token');
        authToken = null;
        updateAuthUI(null);
    }
}

function updateAuthUI(user) {
    const statusEl = document.getElementById('connection-status');
    if (user) {
        statusEl.innerHTML = `
            <span class="status-dot"></span>
            <span class="status-text">${user.email}</span>
            <button onclick="logout()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;margin-left:8px;font-size:0.8rem;">Logout</button>
        `;
    }
}

function openAuthModal() {
    document.getElementById('auth-modal').classList.add('open');
    isLoginMode = true;
    updateAuthForm();
}

function closeAuthModal() {
    document.getElementById('auth-modal').classList.remove('open');
    document.getElementById('auth-form').reset();
}

function toggleAuthMode() {
    isLoginMode = !isLoginMode;
    updateAuthForm();
}

function updateAuthForm() {
    document.getElementById('auth-title').textContent = isLoginMode ? 'Sign In' : 'Create Account';
    document.getElementById('auth-subtitle').textContent = isLoginMode ? 'Welcome back to BioLinker' : 'Start your biomarker discovery journey';
    document.getElementById('auth-btn-text').textContent = isLoginMode ? 'Sign In' : 'Create Account';
    document.getElementById('auth-switch-text').textContent = isLoginMode ? "Don't have an account?" : 'Already have an account?';
    document.getElementById('auth-switch-btn').textContent = isLoginMode ? 'Sign Up' : 'Sign In';
    document.getElementById('name-group').style.display = isLoginMode ? 'none' : 'block';
    document.getElementById('org-group').style.display = isLoginMode ? 'none' : 'block';
}

async function handleAuth(e) {
    e.preventDefault();
    
    const email = document.getElementById('auth-email').value;
    const password = document.getElementById('auth-password').value;
    
    try {
        let result;
        if (isLoginMode) {
            result = await apiCall('/auth/login', {
                method: 'POST',
                body: JSON.stringify({ email, password }),
            });
        } else {
            const full_name = document.getElementById('auth-name').value;
            const organization = document.getElementById('auth-org').value;
            result = await apiCall('/auth/register', {
                method: 'POST',
                body: JSON.stringify({ email, password, full_name, organization }),
            });
        }
        
        authToken = result.access_token;
        localStorage.setItem('biolinker_token', authToken);
        closeAuthModal();
        checkAuth();
        showToast(isLoginMode ? 'Welcome back!' : 'Account created!', 'success');
        
    } catch (error) {
        showToast(error.message || 'Authentication failed', 'error');
    }
}

function logout() {
    localStorage.removeItem('biolinker_token');
    authToken = null;
    currentUser = null;
    updateAuthUI(null);
    showToast('Logged out', 'info');
    checkAPIHealth();
}

function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            switchView(link.dataset.view);
        });
    });
    
    document.getElementById('search-query')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchPubMed();
    });
    
    document.getElementById('explore-search')?.addEventListener('input', debounce((e) => {
        const activeTab = document.querySelector('.tab.active')?.dataset.tab;
        if (activeTab === 'markers') loadMarkers(e.target.value);
        else if (activeTab === 'diseases') loadDiseases(e.target.value);
    }, 300));
    
    document.getElementById('processed-only')?.addEventListener('change', loadArticles);
}

function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`${tab.dataset.tab}-content`)?.classList.add('active');
            
            const tabName = tab.dataset.tab;
            if (tabName === 'markers') loadMarkers();
            else if (tabName === 'diseases') loadDiseases();
            else if (tabName === 'articles') loadArticles();
        });
    });
}

function initNetworkToggle() {
    document.querySelectorAll('.type-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

// === View Management ===
function switchView(viewName) {
    document.querySelectorAll('.nav-link').forEach(l => {
        l.classList.toggle('active', l.dataset.view === viewName);
    });
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === `${viewName}-view`);
    });
    
    if (viewName === 'home') loadDashboard();
    else if (viewName === 'explore') loadMarkers();
}

// === API Functions ===
async function apiCall(endpoint, options = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!response.ok) throw new Error(`API Error: ${response.status}`);
    return response.json();
}

async function checkAPIHealth() {
    const statusEl = document.getElementById('connection-status');
    try {
        await apiCall('/health');
        statusEl.innerHTML = '<span class="status-dot"></span><span class="status-text">Connected</span>';
    } catch {
        statusEl.innerHTML = '<span class="status-dot error"></span><span class="status-text">Offline</span>';
    }
}

// === Dashboard ===
async function loadDashboard() {
    try {
        const stats = await apiCall('/stats');
        animateNumber('stat-articles', stats.articles);
        animateNumber('stat-processed', stats.articles_processed);
        animateNumber('stat-markers', stats.markers);
        animateNumber('stat-diseases', stats.diseases);
        animateNumber('stat-associations', stats.associations);
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

function animateNumber(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    
    const duration = 1000;
    const start = parseInt(el.textContent) || 0;
    const startTime = performance.now();
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased).toLocaleString();
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// === Search ===
function setSearchQuery(query) {
    document.getElementById('search-query').value = query;
    document.getElementById('search-query').focus();
}

async function searchPubMed() {
    const query = document.getElementById('search-query').value.trim();
    if (!query) return showToast('Please enter a search query', 'info');
    
    const container = document.getElementById('search-results');
    container.innerHTML = '<div class="search-placeholder"><div class="spinner"></div><p>Searching PubMed...</p></div>';
    
    try {
        const result = await apiCall('/search', {
            method: 'POST',
            body: JSON.stringify({
                query,
                max_results: parseInt(document.getElementById('max-results').value),
                diseases: document.getElementById('disease-filter').value ? [document.getElementById('disease-filter').value] : null,
                marker_types: document.getElementById('marker-type-filter').value ? [document.getElementById('marker-type-filter').value] : null,
            }),
        });
        
        container.innerHTML = `
            <div class="search-result-card success" style="text-align: center; padding: 3rem;">
                <div style="width: 72px; height: 72px; background: rgba(52, 211, 153, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>
                    </svg>
                </div>
                <h3 style="color: #34d399; margin-bottom: 0.5rem; font-size: 1.75rem; font-weight: 600;">Search Complete!</h3>
                <p style="font-size: 1.2rem; margin-bottom: 0.5rem; color: #fafaf9;">
                    Found <strong>${result.total_count.toLocaleString()}</strong> articles
                </p>
                <p style="color: #a8a29e; margin-bottom: 2rem;">
                    Now importing <strong>${result.articles_fetched.toLocaleString()}</strong> articles into your database...
                </p>
                
                <div style="background: #292524; border-radius: 16px; padding: 1.5rem; margin-bottom: 2rem; text-align: left;">
                    <h4 style="color: #fafaf9; margin-bottom: 1rem; font-size: 1rem; text-align: center;">📋 Next Steps</h4>
                    <div style="display: flex; flex-direction: column; gap: 1rem;">
                        <div style="display: flex; align-items: center; gap: 1rem;">
                            <span style="width: 32px; height: 32px; background: linear-gradient(135deg, #2dd4bf, #38bdf8); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; color: #0c0a09; flex-shrink: 0;">1</span>
                            <span style="color: #a8a29e;">Wait ~30 seconds for articles to finish importing</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 1rem;">
                            <span style="width: 32px; height: 32px; background: linear-gradient(135deg, #2dd4bf, #38bdf8); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; color: #0c0a09; flex-shrink: 0;">2</span>
                            <span style="color: #a8a29e;"><strong style="color: #fafaf9;">Click the button below</strong> to extract biomarkers with AI</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 1rem;">
                            <span style="width: 32px; height: 32px; background: linear-gradient(135deg, #2dd4bf, #38bdf8); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; color: #0c0a09; flex-shrink: 0;">3</span>
                            <span style="color: #a8a29e;">Explore your biomarker-disease knowledge network!</span>
                        </div>
                    </div>
                </div>
                
                <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                    <button class="btn btn-primary" onclick="processArticlesWithProgress()" style="padding: 1rem 2rem; font-size: 1rem;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4"/>
                        </svg>
                        Process Articles with AI
                    </button>
                    <button class="btn btn-ghost" onclick="switchView('explore'); setTimeout(() => document.querySelector('[data-tab=articles]')?.click(), 100);">
                        View Imported Articles
                    </button>
                </div>
            </div>
        `;
        showToast(`Found ${result.total_count.toLocaleString()} articles`, 'success');
        setTimeout(loadDashboard, 3000);
    } catch (error) {
        container.innerHTML = `<div class="search-placeholder"><p style="color: var(--rose);">Search failed: ${error.message}</p></div>`;
        showToast('Search failed', 'error');
    }
}

// === Process Articles ===
async function processArticles() {
    try {
        await apiCall('/articles/process', { method: 'POST', body: JSON.stringify({ limit: 10 }) });
        showToast('Processing articles with AI...', 'success');
        setTimeout(loadDashboard, 5000);
    } catch (error) {
        showToast('Failed to start processing', 'error');
    }
}

async function resetAndProcessArticles() {
    showToast('Resetting failed articles...', 'info');
    
    try {
        // First reset failed articles
        const resetResult = await apiCall('/articles/reset-all', { method: 'POST' });
        showToast(`Reset ${resetResult.reset_count} articles`, 'success');
        
        // Then process them
        setTimeout(() => processArticlesWithProgress(), 1000);
    } catch (error) {
        showToast('Reset failed: ' + error.message, 'error');
    }
}

async function processArticlesWithProgress() {
    const container = document.getElementById('search-results');
    
    container.innerHTML = `
        <div class="search-result-card" style="text-align: center; padding: 3rem;">
            <div class="spinner" style="width: 48px; height: 48px; margin: 0 auto 1.5rem; border-width: 3px;"></div>
            <h3 style="color: #fafaf9; margin-bottom: 0.5rem; font-size: 1.5rem;">Processing Articles...</h3>
            <p style="color: #a8a29e; margin-bottom: 1rem;">Our AI is reading abstracts and extracting biomarkers</p>
            <p style="color: #78716c; font-size: 0.9rem;">This typically takes 20-60 seconds per article</p>
        </div>
    `;
    
    try {
        await apiCall('/articles/process', { method: 'POST', body: JSON.stringify({ limit: 10 }) });
        
        container.innerHTML = `
            <div class="search-result-card success" style="text-align: center; padding: 3rem;">
                <div style="width: 72px; height: 72px; background: rgba(52, 211, 153, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2">
                        <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4"/>
                    </svg>
                </div>
                <h3 style="color: #34d399; margin-bottom: 0.5rem; font-size: 1.5rem;">Processing Started!</h3>
                <p style="color: #a8a29e; margin-bottom: 2rem;">
                    The AI is now extracting biomarkers in the background.<br>
                    Results will appear in the Explore tab as they're ready.
                </p>
                <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                    <button class="btn btn-primary" onclick="switchView('explore')">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/>
                        </svg>
                        Explore Biomarkers
                    </button>
                    <button class="btn btn-ghost" onclick="switchView('network')">
                        View Network Graph
                    </button>
                </div>
            </div>
        `;
        
        showToast('AI extraction started! Check Explore tab for results.', 'success');
        
        // Refresh stats periodically
        let count = 0;
        const interval = setInterval(() => {
            loadDashboard();
            count++;
            if (count >= 12) clearInterval(interval); // Stop after 1 minute
        }, 5000);
        
    } catch (error) {
        container.innerHTML = `
            <div class="search-result-card" style="text-align: center; padding: 3rem; border-color: #fb7185;">
                <h3 style="color: #fb7185; margin-bottom: 0.5rem;">Processing Failed</h3>
                <p style="color: #a8a29e;">${error.message}</p>
                <p style="color: #78716c; font-size: 0.9rem; margin-top: 1rem;">Make sure Ollama is running with the ministral-3b model</p>
                <button class="btn btn-ghost" onclick="processArticlesWithProgress()" style="margin-top: 1rem;">Try Again</button>
            </div>
        `;
        showToast('Processing failed', 'error');
    }
}

// === Data Loading ===
async function loadMarkers(search = '') {
    const container = document.getElementById('markers-list');
    try {
        const markers = await apiCall(`/markers?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (!markers.length) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M12 2L2 7l10 5 10-5-10-5z"/></svg></div><h3>No biomarkers yet</h3><p>Search and process articles to discover biomarkers</p><button class="btn btn-primary" onclick="switchView('search')">Start Searching</button></div>`;
            return;
        }
        
        container.innerHTML = markers.map(m => `
            <div class="data-card" onclick="viewMarkerNetwork('${m.symbol || m.name}')">
                <div class="data-card-header">
                    <span class="data-card-title">${m.symbol || m.name}</span>
                    <span class="data-card-badge badge-${m.marker_type}">${m.marker_type}</span>
                </div>
                <div class="data-card-meta">
                    <span>${m.association_count} associations</span>
                    ${m.hgnc_id ? `<span class="mono">${m.hgnc_id}</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Failed to load markers</p></div>';
    }
}

async function loadDiseases(search = '') {
    const container = document.getElementById('diseases-list');
    try {
        const diseases = await apiCall(`/diseases?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (!diseases.length) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0016.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 002 8.5c0 2.3 1.5 4.05 3 5.5l7 7 7-7z"/></svg></div><h3>No diseases yet</h3><p>Process articles to extract disease associations</p></div>`;
            return;
        }
        
        container.innerHTML = diseases.map(d => `
            <div class="data-card" onclick="viewDiseaseNetwork('${d.name}')">
                <div class="data-card-header">
                    <span class="data-card-title">${d.name}</span>
                </div>
                <div class="data-card-meta">
                    <span>${d.association_count} associations</span>
                    ${d.category ? `<span>${d.category}</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Failed to load diseases</p></div>';
    }
}

async function loadArticles() {
    const container = document.getElementById('articles-list');
    const processedOnly = document.getElementById('processed-only')?.checked || false;
    
    try {
        const articles = await apiCall(`/articles?limit=30&processed_only=${processedOnly}`);
        
        if (!articles.length) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg></div><h3>No articles yet</h3><p>Search PubMed to import articles</p><button class="btn btn-primary" onclick="switchView('search')">Search PubMed</button></div>`;
            return;
        }
        
        container.innerHTML = articles.map(a => `
            <div class="article-card">
                <div class="article-title">${a.title}</div>
                <div class="article-abstract">${a.abstract || 'No abstract'}</div>
                <div class="article-footer">
                    <div class="article-meta">
                        <span class="mono">PMID: ${a.pmid}</span>
                        <span>${a.journal || 'Unknown'}</span>
                        <span>${a.publication_year || 'N/A'}</span>
                    </div>
                    <span class="article-status ${a.is_processed ? 'status-processed' : 'status-pending'}">
                        ${a.is_processed ? '✓ Processed' : '○ Pending'}
                    </span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Failed to load articles</p></div>';
    }
}

// === Network ===
async function loadNetwork() {
    const search = document.getElementById('network-search').value.trim();
    const type = document.querySelector('.type-btn.active')?.dataset.type || 'marker';
    
    if (!search) return showToast('Enter a marker or disease name', 'info');
    
    const container = document.getElementById('network-container');
    container.innerHTML = '<div class="network-placeholder"><div class="spinner"></div><p>Loading network...</p></div>';
    
    try {
        const endpoint = type === 'marker' ? `/network/marker/${encodeURIComponent(search)}` : `/network/disease/${encodeURIComponent(search)}`;
        const data = await apiCall(endpoint);
        
        if (!data.nodes || data.nodes.length === 0 || (data.nodes.length === 1 && data.edges.length === 0)) {
            container.innerHTML = `
                <div class="network-placeholder">
                    <h3>No connections found for "${search}"</h3>
                    <p>This ${type} exists but has no associations yet.</p>
                    <p style="margin-top: 1rem; font-size: 0.85rem; color: var(--text-muted);">
                        Try processing more articles to discover connections.
                    </p>
                </div>`;
            return;
        }
        
        renderNetwork(container, data);
    } catch (error) {
        container.innerHTML = `
            <div class="network-placeholder">
                <h3>"${search}" not found</h3>
                <p>No ${type} with this name exists in your database.</p>
                <p style="margin-top: 1rem; font-size: 0.85rem; color: var(--text-muted);">
                    Make sure you've searched PubMed and processed articles first.
                </p>
                <button class="btn btn-primary" style="margin-top: 1.5rem;" onclick="switchView('search')">
                    Search PubMed
                </button>
            </div>`;
    }
}

function viewMarkerNetwork(symbol) {
    document.getElementById('network-search').value = symbol;
    document.querySelector('.type-btn[data-type="marker"]').click();
    switchView('network');
    loadNetwork();
}

function viewDiseaseNetwork(name) {
    document.getElementById('network-search').value = name;
    document.querySelector('.type-btn[data-type="disease"]').click();
    switchView('network');
    loadNetwork();
}

function renderNetwork(container, data) {
    if (!data.nodes?.length) {
        container.innerHTML = '<div class="network-placeholder"><p>No connections found</p></div>';
        return;
    }
    
    const width = container.clientWidth;
    const height = 500;
    const centerX = width / 2;
    const centerY = height / 2;
    
    const nodes = data.nodes.map((n, i) => {
        const angle = (i * 2 * Math.PI) / data.nodes.length;
        const radius = i === 0 ? 0 : 150;
        return { ...n, x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius };
    });
    
    const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]));
    
    let svg = `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:100%;">`;
    
    // Draw edges
    data.edges.forEach(e => {
        const s = nodeMap[e.source], t = nodeMap[e.target];
        if (s && t) svg += `<line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>`;
    });
    
    // Draw nodes
    nodes.forEach(n => {
        const color = n.type === 'marker' ? '#a78bfa' : '#fb7185';
        const r = n.type === 'marker' ? 24 : 20;
        svg += `
            <g style="cursor:pointer" onclick="alert('${n.label}')">
                <circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${color}" opacity="0.9"/>
                <circle cx="${n.x}" cy="${n.y}" r="${r + 8}" fill="${color}" opacity="0.1"/>
                <text x="${n.x}" y="${n.y + r + 18}" text-anchor="middle" fill="#a8a29e" font-size="11" font-family="Inter">${n.label}</text>
            </g>
        `;
    });
    
    svg += '</svg>';
    container.innerHTML = svg;
}

// === Enrichment Modal ===
function openEnrichModal() {
    document.getElementById('enrich-modal').classList.add('open');
    document.getElementById('enrich-results').innerHTML = '';
}

function closeEnrichModal() {
    document.getElementById('enrich-modal').classList.remove('open');
}

function setEnrichSymbol(symbol) {
    document.getElementById('enrich-symbol').value = symbol;
    enrichMarker();
}

async function enrichMarker() {
    const symbol = document.getElementById('enrich-symbol').value.trim();
    if (!symbol) return showToast('Enter a gene symbol', 'info');
    
    const container = document.getElementById('enrich-results');
    container.innerHTML = '<div style="text-align:center;padding:2rem;"><div class="spinner"></div></div>';
    
    try {
        const data = await apiCall('/enrich/marker', {
            method: 'POST',
            body: JSON.stringify({ marker_name: symbol, marker_type: 'gene' }),
        });
        
        let html = '';
        
        if (data.hgnc) {
            html += `
                <div class="lookup-section">
                    <div class="lookup-section-title">HGNC Gene Information</div>
                    <div class="lookup-grid">
                        <div class="lookup-item"><span class="lookup-item-label">Symbol</span><span class="lookup-item-value highlight">${data.hgnc.symbol}</span></div>
                        <div class="lookup-item"><span class="lookup-item-label">HGNC ID</span><span class="lookup-item-value">${data.hgnc.hgnc_id}</span></div>
                        <div class="lookup-item full-width"><span class="lookup-item-label">Name</span><span class="lookup-item-value">${data.hgnc.name}</span></div>
                        <div class="lookup-item"><span class="lookup-item-label">Locus Type</span><span class="lookup-item-value">${data.hgnc.locus_type}</span></div>
                        <div class="lookup-item"><span class="lookup-item-label">Chromosome</span><span class="lookup-item-value">${data.hgnc.chromosome || 'N/A'}</span></div>
                    </div>
                </div>
            `;
        }
        
        if (data.uniprot) {
            html += `
                <div class="lookup-section">
                    <div class="lookup-section-title">UniProt Protein Information</div>
                    <div class="lookup-grid">
                        <div class="lookup-item"><span class="lookup-item-label">Accession</span><span class="lookup-item-value highlight">${data.uniprot.uniprot_id}</span></div>
                        <div class="lookup-item"><span class="lookup-item-label">Entry</span><span class="lookup-item-value">${data.uniprot.entry_name}</span></div>
                        <div class="lookup-item full-width"><span class="lookup-item-label">Protein Name</span><span class="lookup-item-value">${data.uniprot.protein_name}</span></div>
                        ${data.uniprot.function ? `<div class="lookup-item full-width"><span class="lookup-item-label">Function</span><span class="lookup-item-value" style="font-family:var(--font-body);line-height:1.6">${data.uniprot.function}</span></div>` : ''}
                    </div>
                </div>
            `;
        }
        
        if (!html) html = '<div style="text-align:center;padding:2rem;color:var(--text-muted)">No information found</div>';
        container.innerHTML = html;
        
    } catch (error) {
        container.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--rose)">Lookup failed: ${error.message}</div>`;
    }
}

// === Utilities ===
function debounce(fn, delay) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), delay);
    };
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type]}</span><span class="toast-message">${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Global exports
window.switchView = switchView;
window.searchPubMed = searchPubMed;
window.setSearchQuery = setSearchQuery;
window.processArticles = processArticles;
window.processArticlesWithProgress = processArticlesWithProgress;
window.resetAndProcessArticles = resetAndProcessArticles;
window.loadNetwork = loadNetwork;
window.viewMarkerNetwork = viewMarkerNetwork;
window.viewDiseaseNetwork = viewDiseaseNetwork;
window.openEnrichModal = openEnrichModal;
window.closeEnrichModal = closeEnrichModal;
window.setEnrichSymbol = setEnrichSymbol;
window.enrichMarker = enrichMarker;
window.openAuthModal = openAuthModal;
window.closeAuthModal = closeAuthModal;
window.toggleAuthMode = toggleAuthMode;
window.handleAuth = handleAuth;
window.logout = logout;
