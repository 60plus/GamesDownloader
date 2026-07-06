<template>
  <teleport to="body">
    <transition name="about-fade">
      <div v-if="aboutOpen" class="about-overlay" @click.self="closeAbout">
        <div class="about-modal glass">
          <button class="about-close" @click="closeAbout">&times;</button>

          <img src="/GDLOGO.png" class="about-gdlogo" alt="GamesDownloader" />
          <div v-if="version" class="about-version">{{ t('about.version') }} {{ version }}</div>

          <p class="about-tagline">{{ t('about.tagline') }}</p>
          <p class="about-body">{{ t('about.body') }}</p>

          <a class="about-discord" href="https://discord.gg/vdFz5N6CQY" target="_blank" rel="noopener">
            <img src="/about/discord.png" class="about-discord-icon" alt="Discord" />
            <span>{{ t('about.discord') }}</span>
          </a>

          <div class="about-sep" />
          <div class="about-created">created by</div>
          <img src="/about/60plus.png" class="about-author" alt="60plus" />
          <div class="about-year">&copy; 2026</div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import client from "@/services/api/client";
import { useI18n } from "@/i18n";
import { aboutOpen, closeAbout } from "@/lib/about";

const { t } = useI18n();
const version = ref("");

watch(aboutOpen, async (open) => {
  if (!open || version.value) return;
  try {
    const { data } = await client.get("/health");
    version.value = data?.version || "";
  } catch { /* version stays hidden */ }
});
</script>

<style scoped>
.about-overlay {
  position: fixed; inset: 0; z-index: 950;
  background: rgba(0, 0, 0, .6);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.about-modal {
  position: relative;
  width: 92%; max-width: 420px;
  max-height: 88vh; overflow-y: auto;
  background: var(--bg2, #0f0f1a);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, .1));
  border-radius: var(--radius, 12px);
  padding: 34px 30px 28px;
  display: flex; flex-direction: column; align-items: center;
  text-align: center;
  box-shadow: 0 12px 48px rgba(0, 0, 0, .5);
}
.about-close {
  position: absolute; top: 10px; right: 14px;
  background: none; border: none;
  color: var(--muted); font-size: 24px; cursor: pointer;
  transition: color .15s;
}
.about-close:hover { color: var(--text); }

.about-gdlogo { height: 130px; max-width: 80%; object-fit: contain; }
.about-version {
  margin-top: 10px;
  padding: 3px 12px; border-radius: 99px;
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  background: color-mix(in srgb, var(--pl) 15%, transparent);
  color: var(--pl-light, #fff);
  font-size: 12px; font-weight: 600;
}

.about-tagline {
  margin: 20px 0 0;
  font-size: 15px; font-weight: 700; color: var(--text);
  text-wrap: balance; /* no lonely last word in longer languages */
}
.about-body {
  margin: 10px 0 0;
  font-size: 13px; line-height: 1.65; color: var(--muted);
}

.about-discord {
  margin-top: 20px;
  display: inline-flex; align-items: center; gap: 10px;
  padding: 4px 14px; border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--pl-light, #fff);
  font-size: 13px; font-weight: 600; text-decoration: none;
  transition: all .15s;
}
.about-discord:hover {
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  border-color: color-mix(in srgb, var(--pl) 55%, transparent);
  color: #fff;
}
.about-discord-icon { width: 64px; height: 64px; border-radius: 12px; }

.about-sep {
  width: 60%; height: 1px; margin: 22px 0 16px;
  background: var(--glass-border, rgba(255, 255, 255, .1));
}
.about-created {
  font-size: 11px; font-weight: 600; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted);
}
/* source PNG is cropped to the artwork (no baked-in margins), so these small
   gaps are the real spacing */
.about-author { width: 200px; height: auto; object-fit: contain; margin-top: 8px; }
.about-year { margin-top: 6px; font-size: 12px; color: var(--muted); }

.about-fade-enter-active { transition: opacity .2s ease; }
.about-fade-leave-active { transition: opacity .15s ease; }
.about-fade-enter-from, .about-fade-leave-to { opacity: 0; }
.about-fade-enter-active .about-modal { transition: transform .2s ease; }
.about-fade-enter-from .about-modal { transform: scale(.95); }
</style>
