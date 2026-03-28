/* ==========================================================================
   ACCOUNTS MODULE - Account-Management
========================================================================== */

const accounts = (() => {
  let _users = [];
  let _editingUserId = null;
  
  async function _loadUsers() {
    const container = ui.el('accounts-content');
    container.innerHTML = '<div class="panel__loading">Wird geladen ...</div>';
    
    try {
      _users = await api.getUsers();
      console.log('Users loaded:', _users.length);
      ui.renderAccountsList(_users);
    } catch (err) {
      console.error('Error loading users:', err);
      container.innerHTML = '<div class="panel__placeholder">Fehler beim Laden der Accounts.</div>';
    }
  }

  function _openCreateModal() {
    _editingUserId = null;
    ui.openAccountModal({
      title: 'Neuer Account',
      editMode: false
    });
    const form = ui.el('account-form');
    if (form) {
      form.onsubmit = (e) => _saveAccount(e, null);
    }
  }

  function _openEditModal(userId) {
    const user = _users.find(u => u.id === userId);
    if (!user) {
      ui.toast('Account nicht gefunden.', 'error');
      return;
    }
    _editingUserId = userId;
    ui.openAccountModal({
      title: 'Account bearbeiten',
      username: user.username,
      email: user.email,
      isActive: user.is_active,
      isSuperuser: user.is_superuser,
      isTechnicalContact: user.is_technical_contact,
      editMode: true
    });
    const form = ui.el('account-form');
    if (form) {
      form.onsubmit = (e) => _saveAccount(e, userId);
    }
  }

  async function _saveAccount(e, userId) {
    e.preventDefault();
    const form = e.currentTarget;
    const username = form.elements['username'].value.trim();
    const email = form.elements['email'].value.trim();
    const password = form.elements['password'].value;
    const isActive = form.elements['is_active'].checked;
    const isSuperuser = form.elements['is_superuser'].checked;
    const isTechnicalContact = form.elements['is_technical_contact'].checked;

    ui.setModalError(null);
    if (!email) {
      ui.setModalError('Bitte E-Mail eingeben.');
      return;
    }
    if (!userId && !username) {
      ui.setModalError('Bitte Benutzername eingeben.');
      return;
    }
    if (!userId && !password) {
      ui.setModalError('Bitte Passwort eingeben.');
      return;
    }

    ui.setModalBusy(true);
    try {
      if (!userId) {
        // Create: use register endpoint, then patch flags if non-default
        const created = await api.createUser({ username, email, password });
        if (!isActive || isSuperuser || isTechnicalContact) {
          await api.updateUser(created.id, {
            is_active: isActive,
            is_superuser: isSuperuser,
            is_technical_contact: isTechnicalContact
          });
        }
      } else {
        const patch = {
          email,
          is_active: isActive,
          is_superuser: isSuperuser,
          is_technical_contact: isTechnicalContact
        };
        if (password) patch.password = password;
        await api.updateUser(userId, patch);
      }
      ui.closeAccountModal();
      await _loadUsers();
      ui.toast(userId ? 'Account aktualisiert.' : 'Account erstellt.', 'success');
    } catch (err) {
      ui.setModalError(err.message);
    } finally {
      ui.setModalBusy(false);
    }
  }

  async function _confirmDelete(userId) {
    const user = _users.find(u => u.id === userId);
    if (!user) return;

    const confirmed = await ui.openConfirmModal(
      `Account „${user.username}" wirklich löschen? Diese Aktion ist unwiderruflich.`,
      'Account löschen'
    );

    if (!confirmed) return;

    try {
      await api.deleteUser(userId);
      await _loadUsers();
      ui.toast(`Account „${user.username}" wurde gelöscht.`);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  function init() {
    console.log('Accounts module initialized');
  }

  async function load() {
    await _loadUsers();
  }

  function handleContentClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = parseInt(btn.dataset.id, 10);
    if (btn.dataset.action === 'edit') _openEditModal(id);
    if (btn.dataset.action === 'delete') _confirmDelete(id);
  }

  function openCreateModal() {
    _openCreateModal();
  }

  return { init, load, handleContentClick, openCreateModal };
})();