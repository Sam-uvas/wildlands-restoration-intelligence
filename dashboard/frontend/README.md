# WILDLANDS — Central API Configuration

## Purpose

All frontend modules should use `config.js` instead of hard-coding:

```text
http://localhost:8000
```

Include this before the page's own JavaScript:

```html
<script src="config.js"></script>
```

Then replace:

```js
const API_URL = "http://localhost:8000";
fetch(API_URL + "/api/observations");
```

with:

```js
fetch(apiUrl("/api/observations"));
```

## Production

The configuration supports a runtime override:

```html
<script>
  window.WILDLANDS_API_BASE_URL = "https://YOUR-DEPLOYED-API.example.com";
</script>
<script src="config.js"></script>
```

This means the same frontend can point to a development or production API without editing every page.

## Important

Do not put database credentials in this file.

The browser should only know the public API URL. PostgreSQL/PostGIS credentials remain on the backend/server.
