(function () {
  function getVersionRoot(pathname) {
    var cleaned = pathname.replace(/\/+$/g, "").replace(/\/+/g, "/");
    var parts = cleaned.split("/").filter(Boolean);

    for (var i = 0; i < parts.length; i += 1) {
      if (parts[i] === "latest" || /^v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(parts[i])) {
        return {
          prefixParts: parts.slice(0, i),
          version: parts[i],
          tailParts: parts.slice(i + 1),
        };
      }
    }

    return {
      prefixParts: [],
      version: "latest",
      tailParts: parts,
    };
  }

  function buildTarget(prefixParts, version, languageCode, contentParts) {
    var parts = prefixParts.concat([version, languageCode]).concat(contentParts);
    var target = "/" + parts.join("/");
    if (contentParts.length === 0) {
      target += "/";
    }
    return target.replace(/\/+/g, "/");
  }

  function createSelector(languages, currentLanguage, routeInfo, hasLanguageSegment, contentParts) {
    var container = document.createElement("div");
    container.id = "docs-language-switcher";
    container.className = "docs-language-switcher";

    var label = document.createElement("label");
    label.htmlFor = "docs-language-select";
    label.className = "docs-language-switcher__label";
    label.textContent = "Sprache";

    var select = document.createElement("select");
    select.id = "docs-language-select";
    select.className = "docs-language-switcher__select";
    select.setAttribute("aria-label", "Documentation language");

    languages.forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry;
      option.textContent = entry;
      if (entry === currentLanguage) {
        option.selected = true;
      }
      select.appendChild(option);
    });

    if (languages.length <= 1) {
      select.disabled = true;
    }

    select.addEventListener("change", function () {
      if (languages.length <= 1 && !hasLanguageSegment) {
        return;
      }

      var selected = select.value;
      var target = buildTarget(routeInfo.prefixParts, routeInfo.version, selected, contentParts);
      window.location.href = target;
    });

    container.appendChild(label);
    container.appendChild(select);
    document.body.appendChild(container);
  }

  function initLanguageSelector() {
    var routeInfo = getVersionRoot(window.location.pathname);
    var languagesUrl = "/" + routeInfo.prefixParts.join("/") + "/languages.json";
    languagesUrl = languagesUrl.replace(/\/+/g, "/");

    fetch(languagesUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("languages.json could not be loaded");
        }
        return response.json();
      })
      .catch(function () {
        var htmlLang = document.documentElement.lang || "de";
        return [htmlLang];
      })
      .then(function (languages) {
        if (!Array.isArray(languages) || languages.length === 0) {
          return;
        }

        var hasLanguageSegment = routeInfo.tailParts.length > 0 && languages.indexOf(routeInfo.tailParts[0]) >= 0;
        var contentParts = hasLanguageSegment ? routeInfo.tailParts.slice(1) : routeInfo.tailParts;
        var currentLanguage = hasLanguageSegment ? routeInfo.tailParts[0] : languages[0];

        createSelector(languages, currentLanguage, routeInfo, hasLanguageSegment, contentParts);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initLanguageSelector);
  } else {
    initLanguageSelector();
  }
})();
