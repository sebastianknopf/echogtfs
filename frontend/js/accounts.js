/* ==========================================================================
   ACCOUNTS MODULE - Account management
========================================================================== */

const accounts = (() => {
  let _users = [];
  let _editingUserId = null;
  
  async function _loadUsers() {
    const container = ui.el('accounts-content');
    container.innerHTML = `<div class="panel__loading">${window.i18n('accounts.loading')}</div>`;
    
    try {
      _users = await api.getUsers();
      ui.renderAccountsList(_users);
    } catch (err) {
      container.innerHTML = `<div class="panel__placeholder">${window.i18n('accounts.error.load')}</div>`;
    }
  }

  function _openCreateModal() {
    _editingUserId = null;
    ui.openAccountModal({
      title: window.i18n('account.modal.create'),
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
      ui.toast(window.i18n('accounts.error.notfound'), 'error');
      return;
    }
    _editingUserId = userId;
    ui.openAccountModal({
      title: window.i18n('account.modal.edit'),
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
      ui.setModalError(window.i18n('account.error.email_required'));
      return;
    }
    if (!userId && !username) {
      ui.setModalError(window.i18n('account.error.username_required'));
      return;
    }
    if (!userId && !password) {
      ui.setModalError(window.i18n('account.error.password_required'));
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
      ui.toast(userId ? window.i18n('accounts.updated') : window.i18n('accounts.created'), 'success');
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
      window.i18n('accounts.delete.confirm', { name: user.username }),
      window.i18n('accounts.delete.title')
    );

    if (!confirmed) return;

    try {
      await api.deleteUser(userId);
      await _loadUsers();
      ui.toast(window.i18n('accounts.deleted', { name: user.username }));
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  function init() {
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