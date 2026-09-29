// ============================================================
// Mock Supabase + Leaflet + JSZip pour les tests Playwright.
// Injecté juste après la balise script de Leaflet dans
// index.html (voir build_preview.py) : remplace le vrai backend par
// des données en mémoire, pour tester l'appli sans réseau ni vraie
// base Supabase. Ne modifie jamais index.html lui-même.
// ============================================================

// ---------- Jeu de données de test (30 objets, quelques souhaits) ----------
window.__FAKE_ROWS__ = Array.from({ length: 30 }, (_, i) => ({
  uid: `uid-${String(i).padStart(3, '0')}`,
  id_public: `FFI-${1000 + i}`,
  titre: `Objet test ${i}`,
  type_objet: ['Insigne', 'Brassard', 'Médaille', 'Document', 'Livre'][i % 5],
  region: ['Bretagne', 'Occitanie', 'Île-de-France', 'Normandie'][i % 4],
  departement: ['35 Ille-et-Vilaine', '31 Haute-Garonne', '75 Paris', '76 Seine-Maritime'][i % 4],
  fabricant: i % 3 === 0 ? null : 'Arthus-Bertrand',
  provenance: 'Salon numismatique',
  prix_achat: i % 4 === 0 ? null : 50 + i * 10,
  valeur_estimee_actuelle: i % 5 === 0 ? null : 80 + i * 12,
  date_acquisition: '2022-04-29',
  date_estimation: '2023-08-08',
  indice_rarete: ['X', 'XX', 'XXX', 'XXXX', 'M'][i % 5],
  etat_conservation: 'Bon état',
  authenticite: 'Authentique',
  mouvement: 'Réseaux',
  created_at: `2023-0${(i % 9) + 1}-15T10:00:00Z`,
  details: null, taille: '45mm', detail_tirage: null,
  date_fabrication: '1944', type_variante: null, infos: null, notes: null,
}));

window.__FAKE_PHOTOS__ = window.__FAKE_ROWS__.map((o, i) => ({
  id: i + 1, objet_uid: o.uid, storage_path: `${o.uid}/recto.webp`, label: 'Recto', position: 1,
}));

window.__FAKE_WISHLIST__ = [];
window.__FAKE_WISHLIST_PHOTOS__ = [];

// ---------- Client Supabase minimal ----------
window.supabase = {
  createClient: function () {
    function genericTable(store, idPrefix, defaults) {
      function withFilters(run) {
        const filters = [];
        let sortField = null;
        let sortAsc = true;
        let wantSingle = false;
        const chain = {
          eq(field, value) { filters.push([field, value]); return chain; },
          order(field, opts) { sortField = field; sortAsc = !(opts && opts.ascending === false); return chain; },
          single() { wantSingle = true; return chain; },
          maybeSingle() { wantSingle = true; return chain; },
          then(resolve, reject) {
            const matches = (row) => filters.every(([f, v]) => String(row[f]) === String(v));
            return run(matches, sortField, sortAsc, wantSingle).then(resolve, reject);
          },
          catch(reject) { return chain.then(undefined, reject); },
        };
        return chain;
      }
      return {
        select() {
          return withFilters(async (matches, sortField, sortAsc) => {
            let rows = store.filter(matches);
            if (sortField) {
              rows = rows.slice().sort((a, b) => {
                const av = a[sortField], bv = b[sortField];
                if (av === bv) return 0;
                return (av > bv ? 1 : -1) * (sortAsc ? 1 : -1);
              });
            }
            return { data: rows, error: null };
          });
        },
        insert(payload) {
          const rowsIn = Array.isArray(payload) ? payload : [payload];
          const rows = rowsIn.map((p) => {
            const row = Object.assign({}, defaults, p);
            if (idPrefix === 'uid' && !row.uid) row.uid = `${idPrefix}-new-${store.length}`;
            if (idPrefix !== 'uid' && !row.id) row.id = `${idPrefix}-${store.length}`;
            store.push(row);
            return row;
          });
          const single = Array.isArray(payload) ? rows : rows[0];
          return {
            select() {
              return withFiltersOverRows(rows, single);
            },
            then(resolve) { resolve({ data: single, error: null }); },
          };
        },
        update(payload) {
          return withFilters(async (matches) => {
            store.forEach((row) => { if (matches(row)) Object.assign(row, payload); });
            return { data: null, error: null };
          });
        },
        delete() {
          return withFilters(async (matches) => {
            for (let i = store.length - 1; i >= 0; i--) if (matches(store[i])) store.splice(i, 1);
            return { data: null, error: null };
          });
        },
      };

      // select() chained after insert(): no further filtering needed, just
      // supports .single()/.maybeSingle() on the row(s) just inserted.
      function withFiltersOverRows(rows, singleFallback) {
        let wantSingle = false;
        const chain = {
          single() { wantSingle = true; return chain; },
          maybeSingle() { wantSingle = true; return chain; },
          then(resolve) {
            resolve({ data: wantSingle ? singleFallback : rows, error: null });
          },
        };
        return chain;
      }
    }

    const tables = {
      objets: genericTable(window.__FAKE_ROWS__, 'uid', {}),
      objets_public: {
        select: () => {
          const rows = () => window.__FAKE_ROWS__.map(
            ({ prix_achat, valeur_estimee_actuelle, provenance, date_acquisition, reference_catalogue, ...pub }) => pub
          );
          const chain = {
            order() { return chain; },
            eq() { return chain; },
            then(resolve) { resolve({ data: rows(), error: null }); },
          };
          return chain;
        },
      },
      photos: genericTable(window.__FAKE_PHOTOS__, 'photo', {}),
      wishlist: genericTable(window.__FAKE_WISHLIST__, 'wish', {}),
      wishlist_photos: genericTable(window.__FAKE_WISHLIST_PHOTOS__, 'wishphoto', {}),
    };

    let session = null;

    return {
      from(name) {
        if (!tables[name]) throw new Error(`mock_stub: table non gérée "${name}"`);
        return tables[name];
      },
      auth: {
        getSession: async () => ({ data: { session } }),
        signInWithPassword: async ({ email, password }) => {
          if (email === 'admin@test.fr' && password === 'test1234') {
            session = { user: { id: 'admin-uid', email } };
            return { data: { session }, error: null };
          }
          return { data: { session: null }, error: { message: 'Identifiants incorrects' } };
        },
        signOut: async () => { session = null; return { error: null }; },
        updateUser: async () => ({ data: {}, error: null }),
      },
    };
  },
};

// ---------- fetch() : intercepte les photos Scaleway (image factice) ----------
window.__REAL_FETCH__ = window.fetch.bind(window);
window.fetch = function (url, opts) {
  if (typeof url === 'string' && url.includes('collection-ffi-photos')) {
    const blob = new Blob(['fake-photo-bytes'], { type: 'image/webp' });
    return Promise.resolve({ ok: true, status: 200, blob: () => Promise.resolve(blob) });
  }
  return window.__REAL_FETCH__(url, opts);
};

// ---------- Leaflet minimal (pas de vraie carte en test) ----------
window.L = {
  map: () => ({
    setView() { return this; },
    remove() {},
    invalidateSize() {},
    on() { return this; },
  }),
  tileLayer: () => ({ addTo() { return this; } }),
  geoJSON: () => ({ addTo() { return this; }, eachLayer() {}, getBounds: () => ({ getCenter: () => ({}) }) }),
  divIcon: (opts) => ({ __isDivIcon: true, options: opts }),
  marker: (latlng, opts) => { window.__LAST_MARKER__ = { latlng, opts }; return { addTo() { return this; } }; },
  createObjectURL: (b) => (window.URL ? URL.createObjectURL(b) : ''),
  revokeObjectURL: () => {},
};
