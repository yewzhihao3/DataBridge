<template>
  <div class="app">
    <header class="app-header">
      <h1>DataBridge</h1>

      <nav>
        <RouterLink to="/">Ingestion</RouterLink>
        <RouterLink to="/history">History</RouterLink>
        <RouterLink to="/templates">Templates</RouterLink>
      </nav>
    </header>

    <main class="app-content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  border-bottom: 1px solid #e5e7eb;
}

.app-header h1 {
  margin: 0;
  font-size: 24px;
}

nav {
  display: flex;
  gap: 20px;
}

nav a {
  color: #6b7280;
  text-decoration: none;
}

nav a.router-link-active {
  color: #2563eb;
  font-weight: 600;
}

.app-content {
  padding: 32px;
}
</style>