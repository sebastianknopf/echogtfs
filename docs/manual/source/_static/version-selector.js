(function () {
  function getVersionRoot(pathname) {
    var cleaned = pathname.replace(/\/+/g, "/").replace(/\/$/, "");
    var parts = cleaned.split("/").filter(Boolean);

    for (var i = 0; i < parts.length; i += 1) {
      if (parts[i] === "latest" || /^v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(parts[i])) {
        return {
          prefix: "/" + parts.slice(0, i).join("/"),
          version: parts[i],
          suffix: "/" + parts.slice(i + 1).join("/"),
        };
      }
    }

    return {
      prefix: "",
      version: "latest",
      suffix: cleaned ? cleaned : "/",
    };
  }

  function createSelector(versions, currentVersion, versionRoot) {
    var container = document.createElement("div");
    container.id = "docs-version-switcher";
    container.className = "docs-version-switcher";

    var label = document.createElement("label");
    label.htmlFor = "docs-version-select";
    label.className = "docs-version-switcher__label";
    label.textContent = "Version";

    var select = document.createElement("select");
    select.id = "docs-version-select";
    select.className = "docs-version-switcher__select";
    select.setAttribute("aria-label", "Documentation version");

    versions.forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry;
      option.textContent = entry;
      if (entry === currentVersion) {
        option.selected = true;
      }
      select.appendChild(option);
    });

    select.addEventListener("change", function () {
      var selected = select.value;
      var target = (versionRoot.prefix || "") + "/" + selected + (versionRoot.suffix || "/");
      window.location.href = target.replace(/\/+/g, "/");
    });

    container.appendChild(label);
    container.appendChild(select);
    document.body.appendChild(container);
  }

  function initVersionSelector() {
    var root = getVersionRoot(window.location.pathname);
    var versionsUrl = (root.prefix || "") + "/versions.json";

    fetch(versionsUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("versions.json could not be loaded");
        }
        return response.json();
      })
      .then(function (versions) {
        if (!Array.isArray(versions) || versions.length === 0) {
          return;
        }
        createSelector(versions, root.version, root);
      })
      .catch(function () {
        // Keep docs usable even when versions.json is not available.
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initVersionSelector);
  } else {
    initVersionSelector();
  }
})();
