/* ═══════════════════════════════════════════════════════════════════════════
   Échecs IA — frontend
   ═══════════════════════════════════════════════════════════════════════════ */

const PIECES = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
};

const PIECE_VALUES = { P: 1, N: 3, B: 3, R: 5, Q: 9 };

/* ── État de l'application ─────────────────────────────────────────────── */
let G = {
  gid: null,
  state: null,          // dernier état renvoyé par le serveur
  mode: 'vs_ia',
  myColor: 'w',         // couleur du joueur local (vs_ia et local_2p = blanc)
  flipped: false,
  selected: null,       // {r, c} case sélectionnée
  legalTargets: [],     // [{r, c, extra}] cibles légales depuis selected
  pendingPromo: null,   // {from_r, from_c, to_r, to_c, resolve}
  lastMoveUci: null,
  // online
  token: null,
  rid: null,
  pollTimer: null,
};

/* ── Démarrage ────────────────────────────────────────────────────────── */
window.onload = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const username = urlParams.get('username');
  if (username) document.getElementById('inp-name').value = username;
};

/* ── Helpers UI ───────────────────────────────────────────────────────── */
function toast(msg, duration = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

function showNewGame() {
  document.getElementById('modal-new').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
  stopPolling();
}

function closeGameOver() {
  document.getElementById('modal-gameover').style.display = 'none';
  showNewGame();
}

function showElo() {
  fetch('/api/elo').then(r => r.json()).then(data => {
    const list = document.getElementById('elo-list');
    if (!data.length) {
      list.innerHTML = '<div style="padding:12px;color:#64748b;text-align:center">Aucun classement disponible</div>';
    } else {
      list.innerHTML = data.map(([name, rating], i) =>
        `<div class="elo-row">
          <span class="elo-rank">${i + 1}</span>
          <span class="elo-name">${name}</span>
          <span class="elo-rating">${rating}</span>
        </div>`
      ).join('');
    }
    document.getElementById('modal-elo').style.display = 'flex';
  });
}
function closeElo() { document.getElementById('modal-elo').style.display = 'none'; }

function onModeChange() {
  const mode = document.querySelector('input[name=mode]:checked').value;
  document.getElementById('ai-options').style.display = mode === 'vs_ia' ? '' : 'none';
  document.getElementById('p2-options').style.display = mode === 'local_2p' ? '' : 'none';
  document.getElementById('online-options').style.display = mode === 'online' ? '' : 'none';
}

function onOnlineActionChange() {
  const action = document.querySelector('input[name=online-action]:checked').value;
  document.getElementById('join-code-wrap').style.display = action === 'join' ? '' : 'none';
  document.getElementById('btn-start').textContent = action === 'join' ? 'Rejoindre' : 'Créer la salle';
}

/* ── Démarrage d'une partie ────────────────────────────────────────────── */
async function startGame() {
  const mode = document.querySelector('input[name=mode]:checked').value;
  const name = document.getElementById('inp-name').value.trim() || 'Joueur';

  if (mode === 'online') {
    const action = document.querySelector('input[name=online-action]:checked').value;
    if (action === 'create') await createOnlineRoom(name);
    else await joinOnlineRoom(name);
    return;
  }

  const body = { mode: mode === 'vs_ia' ? 'vs_ia' : 'local_2p', p1: name };

  if (mode === 'vs_ia') {
    body.level = document.getElementById('inp-level').value;
    const colorChoice = document.querySelector('input[name=color]:checked').value;
    // si joueur choisit noir, l'IA joue blanc
    body.ai_color = colorChoice === 'w' ? 'b' : 'w';
  } else {
    body.p2 = document.getElementById('inp-p2').value.trim() || 'Joueur 2';
    body.ai_color = null;
  }

  const resp = await fetch('/api/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await resp.json();

  G.gid = data.gid;
  G.mode = mode === 'vs_ia' ? 'vs_ia' : 'local_2p';
  G.token = null;
  G.myColor = body.ai_color === 'w' ? 'b' : 'w'; // si IA blanc → je joue noir
  G.flipped = G.myColor === 'b';

  launchGame(data);
}

async function createOnlineRoom(name) {
  const resp = await fetch('/api/room', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  const room = await resp.json();
  G.rid = room.rid;
  G.token = room.token;
  G.myColor = 'w';
  G.flipped = false;

  // Afficher lobby
  document.getElementById('modal-new').style.display = 'none';
  document.getElementById('lobby-overlay').style.display = 'flex';
  document.getElementById('lobby-code').textContent = room.rid;
  document.getElementById('lobby-title').textContent = 'Salle créée !';

  // Polling jusqu'à ce que quelqu'un rejoigne
  G.pollTimer = setInterval(async () => {
    const r2 = await fetch(`/api/room/${room.rid}`).then(r => r.json());
    if (r2.joined && r2.gid) {
      clearInterval(G.pollTimer);
      document.getElementById('lobby-overlay').style.display = 'none';
      G.gid = r2.gid;
      G.mode = 'online_2p';
      const state = await fetch(`/api/game/${r2.gid}/state?token=${G.token}`).then(r => r.json());
      launchGame(state);
      startOnlinePolling();
    }
  }, 1500);
}

async function joinOnlineRoom(name) {
  const code = document.getElementById('inp-room-code').value.trim().toUpperCase();
  if (!code) { toast('Entrez un code de salle'); return; }

  const resp = await fetch(`/api/room/${code}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!resp.ok) { const e = await resp.json(); toast(e.error || 'Erreur'); return; }
  const data = await resp.json();

  G.gid = data.gid;
  G.token = data.token;
  G.myColor = 'b';
  G.flipped = true;
  G.mode = 'online_2p';

  document.getElementById('modal-new').style.display = 'none';
  const state = await fetch(`/api/game/${data.gid}/state?token=${G.token}`).then(r => r.json());
  launchGame(state);
  startOnlinePolling();
}

function cancelLobby() {
  clearInterval(G.pollTimer);
  document.getElementById('lobby-overlay').style.display = 'none';
  document.getElementById('modal-new').style.display = 'flex';
}

/* ── Lancement de la partie ─────────────────────────────────────────────── */
function launchGame(data) {
  G.state = data;
  G.selected = null;
  G.legalTargets = [];
  G.lastMoveUci = data.ai_uci || null;

  document.getElementById('modal-new').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('mode-badge').textContent =
    G.mode === 'vs_ia' ? 'vs IA' : G.mode === 'local_2p' ? '2 joueurs' : 'En ligne';

  buildCoords();
  renderAll(data);
}

/* ── Coordonnées ────────────────────────────────────────────────────────── */
function buildCoords() {
  const files = ['a','b','c','d','e','f','g','h'];
  const ranks = ['8','7','6','5','4','3','2','1'];

  ['coord-top','coord-bottom'].forEach(id => {
    document.getElementById(id).innerHTML = files.map(f => `<span>${f}</span>`).join('');
  });
  ['coord-left','coord-right'].forEach(id => {
    document.getElementById(id).innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
  });
}

/* ── Rendu complet ──────────────────────────────────────────────────────── */
function renderAll(data) {
  G.state = data;
  renderBoard(data);
  renderPlayers(data);
  renderHistory(data);
  renderStatus(data);
  updateActivePlayer(data);

  if (data.status !== 'playing') {
    setTimeout(() => showGameOver(data), 300);
  }
}

function renderBoard(data) {
  const boardEl = document.getElementById('board');
  boardEl.innerHTML = '';
  const { board, legal, in_check, white_to_move } = data;

  // trouver position du roi en échec
  let checkR = -1, checkC = -1;
  if (in_check) {
    for (let r = 0; r < 8; r++)
      for (let c = 0; c < 8; c++) {
        const p = board[r][c];
        if (white_to_move && p === 'K') { checkR = r; checkC = c; }
        if (!white_to_move && p === 'k') { checkR = r; checkC = c; }
      }
  }

  // derniers coups
  const lastFrom = G.lastMoveUci ? uciToRC(G.lastMoveUci.slice(0,2)) : null;
  const lastTo   = G.lastMoveUci ? uciToRC(G.lastMoveUci.slice(2,4)) : null;

  const targetSet = new Set(G.legalTargets.map(t => `${t.r},${t.c}`));

  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const sq = document.createElement('div');
      sq.className = 'sq ' + ((r + c) % 2 === 0 ? 'light' : 'dark');
      sq.dataset.r = r;
      sq.dataset.c = c;

      // Surbrillances
      if (G.selected && G.selected.r === r && G.selected.c === c) sq.classList.add('selected');
      if (targetSet.has(`${r},${c}`)) sq.classList.add('legal-target');
      if (lastFrom && lastFrom.r === r && lastFrom.c === c) sq.classList.add('last-move');
      if (lastTo && lastTo.r === r && lastTo.c === c) sq.classList.add('last-move');
      if (r === checkR && c === checkC) sq.classList.add('check');

      const piece = board[r][c];
      if (piece) {
        const span = document.createElement('span');
        span.className = 'piece ' + (piece === piece.toUpperCase() ? 'white' : 'black');
        span.textContent = PIECES[piece] || piece;
        sq.appendChild(span);
      } else if (targetSet.has(`${r},${c}`)) {
        // Indicateur case vide
        const dot = document.createElement('div');
        dot.className = 'dot';
        sq.appendChild(dot);
      }

      // Indicateur de capture
      if (piece && targetSet.has(`${r},${c}`)) {
        const ring = document.createElement('div');
        ring.className = 'ring';
        sq.appendChild(ring);
      }

      sq.addEventListener('click', () => onSquareClick(r, c));
      boardEl.appendChild(sq);
    }
  }

  if (G.flipped) boardEl.parentElement.parentElement.classList.add('flipped');
  else boardEl.parentElement.parentElement.classList.remove('flipped');
}

function renderPlayers(data) {
  const { p1, p2 } = data;
  // p1 = blanc (bas), p2 = noir (haut) par défaut
  document.getElementById('name-white').textContent = `♔ ${p1}`;
  document.getElementById('name-black').textContent = `♚ ${p2}`;

  // Elo
  const elos = [];
  fetch('/api/elo').then(r => r.json()).then(list => {
    const map = Object.fromEntries(list);
    const ew = map[p1] || 1200;
    const eb = map[p2] || 1200;
    document.getElementById('elo-white').textContent = `${ew} Elo`;
    document.getElementById('elo-black').textContent = `${eb} Elo`;
  });

  // Pièces capturées
  const captured = computeCaptured(data.board);
  document.getElementById('cap-white').innerHTML = captured.byWhite.map(p => `<span>${PIECES[p.toUpperCase()]}</span>`).join('');
  document.getElementById('cap-black').innerHTML = captured.byBlack.map(p => `<span>${PIECES[p]}</span>`).join('');
}

function computeCaptured(board) {
  const startPieces = { P:8, N:2, B:2, R:2, Q:1, K:1, p:8, n:2, b:2, r:2, q:1, k:1 };
  const current = {};
  for (let r = 0; r < 8; r++)
    for (let c = 0; c < 8; c++) {
      const p = board[r][c];
      if (p) current[p] = (current[p] || 0) + 1;
    }
  const byWhite = [], byBlack = [];
  for (const [p, cnt] of Object.entries(startPieces)) {
    const missing = cnt - (current[p] || 0);
    const arr = p === p.toUpperCase() ? byBlack : byWhite;
    for (let i = 0; i < missing; i++) arr.push(p);
  }
  return { byWhite, byBlack };
}

function renderHistory(data) {
  const moves = data.move_log || [];
  const list = document.getElementById('move-list');
  list.innerHTML = '';
  for (let i = 0; i < moves.length; i += 2) {
    const row = document.createElement('div');
    row.className = 'move-pair';
    const num = Math.floor(i / 2) + 1;
    row.innerHTML = `<span class="move-num">${num}.</span>
      <span class="move-cell">${moves[i]}</span>
      <span class="move-cell">${moves[i+1] || ''}</span>`;
    list.appendChild(row);
  }
  list.scrollTop = list.scrollHeight;
}

function renderStatus(data) {
  const msg = document.getElementById('status-msg');
  if (data.status !== 'playing') { msg.textContent = ''; return; }
  if (data.in_check) {
    msg.textContent = `${data.white_to_move ? '♔ Blancs' : '♚ Noirs'} — Échec !`;
    msg.style.color = '#e74c3c';
  } else {
    msg.textContent = `Tour des ${data.white_to_move ? 'Blancs ♔' : 'Noirs ♚'}`;
    msg.style.color = '';
  }
}

function updateActivePlayer(data) {
  document.getElementById('info-white').classList.toggle('active', data.white_to_move);
  document.getElementById('info-black').classList.toggle('active', !data.white_to_move);

  // Overlay attente tour en ligne
  if (G.mode === 'online_2p' && data.status === 'playing') {
    const myTurn = (G.myColor === 'w') === data.white_to_move;
    document.getElementById('waiting-overlay').style.display = myTurn ? 'none' : 'block';
    const opName = G.myColor === 'w' ? data.p2 : data.p1;
    document.getElementById('waiting-name').textContent = opName;
  } else {
    document.getElementById('waiting-overlay').style.display = 'none';
  }
}

function showGameOver(data) {
  stopPolling();
  const icons = { checkmate: '♟', stalemate: '🤝', draw: '🤝' };
  const titles = { checkmate: 'Échec et mat !', stalemate: 'Pat', draw: 'Nulle' };
  document.getElementById('go-icon').textContent = icons[data.status] || '🏁';
  document.getElementById('go-title').textContent = titles[data.status] || 'Partie terminée';
  document.getElementById('go-reason').textContent = data.reason || '';
  document.getElementById('go-elo').textContent = '';
  document.getElementById('modal-gameover').style.display = 'flex';
}

/* ── Interactions plateau ───────────────────────────────────────────────── */
async function onSquareClick(r, c) {
  const data = G.state;
  if (!data || data.status !== 'playing') return;

  // Bloquer si ce n'est pas mon tour (online)
  if (G.mode === 'online_2p') {
    const myTurn = (G.myColor === 'w') === data.white_to_move;
    if (!myTurn) return;
  }

  // Bloquer si c'est le tour de l'IA
  if (G.mode === 'vs_ia') {
    const aiIsWhite = data.ai_color === 'w';
    if (aiIsWhite === data.white_to_move) return;
  }

  const piece = data.board[r][c];
  const isMyPiece = piece && (data.white_to_move ? piece === piece.toUpperCase() : piece === piece.toLowerCase());

  // Clic sur une cible légale → jouer le coup
  const target = G.legalTargets.find(t => t.r === r && t.c === c);
  if (target && G.selected) {
    await playMove(G.selected.r, G.selected.c, r, c);
    return;
  }

  // Sélection d'une de mes pièces
  if (isMyPiece) {
    G.selected = { r, c };
    const key = `${r},${c}`;
    G.legalTargets = (data.legal[key] || []).map(s => {
      const [rc, extra] = s.split('=');
      const [tr, tc] = rc.split(',').map(Number);
      return { r: tr, c: tc, promo: extra || null };
    });
    renderBoard(data);
    return;
  }

  // Clic ailleurs → désélection
  G.selected = null;
  G.legalTargets = [];
  renderBoard(data);
}

async function playMove(sr, sc, er, ec) {
  // Vérifier si promotion nécessaire
  let promo = null;
  const promos = G.legalTargets
    .filter(t => t.r === er && t.c === ec && t.promo)
    .map(t => t.promo);

  if (promos.length > 0) {
    promo = await askPromotion(promos);
    if (!promo) return;
  }

  const fromFile = 'abcdefgh'[sc];
  const fromRank = 8 - sr;
  const toFile   = 'abcdefgh'[ec];
  const toRank   = 8 - er;
  let uci = `${fromFile}${fromRank}${toFile}${toRank}`;
  if (promo) uci += promo.toLowerCase();

  G.selected = null;
  G.legalTargets = [];

  let resp, newData;
  if (G.mode === 'online_2p') {
    resp = await fetch(`/api/game/${G.gid}/move_as`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: G.token, uci }),
    });
  } else {
    resp = await fetch(`/api/game/${G.gid}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uci }),
    });
  }

  if (!resp.ok) {
    const e = await resp.json();
    toast(e.error || 'Erreur');
    return;
  }
  newData = await resp.json();
  G.lastMoveUci = newData.ai_uci || uci;
  renderAll(newData);
}

function askPromotion(available) {
  return new Promise(resolve => {
    const choices = document.getElementById('promo-choices');
    choices.innerHTML = '';
    // available est une liste comme ['Q','R','B','N'] ou ['q','r','b','n']
    const unique = [...new Set(available.map(p => p.toUpperCase()))];
    unique.forEach(p => {
      const btn = document.createElement('span');
      btn.textContent = PIECES[p] || p;
      btn.style.cursor = 'pointer';
      btn.title = { Q:'Dame', R:'Tour', B:'Fou', N:'Cavalier' }[p] || p;
      btn.onclick = () => {
        document.getElementById('modal-promo').style.display = 'none';
        resolve(p);
      };
      choices.appendChild(btn);
    });
    document.getElementById('modal-promo').style.display = 'flex';
  });
}

/* ── Abandon ────────────────────────────────────────────────────────────── */
async function resign() {
  if (!G.gid || !G.state || G.state.status !== 'playing') return;
  if (!confirm('Voulez-vous vraiment abandonner ?')) return;
  const resp = await fetch(`/api/game/${G.gid}/resign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: G.token }),
  });
  const data = await resp.json();
  stopPolling();
  document.getElementById('go-icon').textContent = '🏳';
  document.getElementById('go-title').textContent = 'Abandon';
  document.getElementById('go-reason').textContent = '';
  const myName = G.myColor === 'w' ? G.state.p1 : G.state.p2;
  document.getElementById('go-elo').textContent = data.elo_w ? `${G.state.p1}: ${data.elo_w}  •  ${G.state.p2}: ${data.elo_b}` : '';
  document.getElementById('modal-gameover').style.display = 'flex';
}

/* ── Retourner le plateau ───────────────────────────────────────────────── */
function flipBoard() {
  G.flipped = !G.flipped;
  renderBoard(G.state);
}

/* ── Polling en ligne ───────────────────────────────────────────────────── */
function startOnlinePolling() {
  stopPolling();
  G.pollTimer = setInterval(async () => {
    if (!G.gid) return;
    const data = await fetch(`/api/game/${G.gid}/state?token=${G.token}`).then(r => r.json());
    // Mettre à jour seulement si quelque chose a changé (nb coups)
    const prevLen = (G.state?.move_log || []).length;
    const newLen  = (data.move_log || []).length;
    if (newLen !== prevLen) {
      G.lastMoveUci = data.move_log?.at(-1) || null;
      renderAll(data);
      if (data.status !== 'playing') stopPolling();
    }
  }, 1500);
}

function stopPolling() {
  if (G.pollTimer) { clearInterval(G.pollTimer); G.pollTimer = null; }
}

/* ── Utilitaires ────────────────────────────────────────────────────────── */
function uciToRC(sq) {
  const c = 'abcdefgh'.indexOf(sq[0]);
  const r = 8 - parseInt(sq[1]);
  return { r, c };
}
