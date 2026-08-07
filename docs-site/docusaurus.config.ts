import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'iCoDer 开发者文档',
  tagline: '面向中国医院的医疗 AI 智能体平台 — 开发者指南',
  favicon: 'img/favicon.ico',

  // Production URL is gated on R6 cloud-only ADR — placeholder for now.
  // Update `url` and `baseUrl` when DNS + TLS are live; deployment itself
  // is OUT OF SCOPE for the current Sprint 1 scaffold.
  url: 'https://docs.icoder.cloud',
  baseUrl: '/',

  // i18n — Chinese first per CLAUDE.md 产品定位
  i18n: {
    defaultLocale: 'zh-CN',
    locales: ['zh-CN'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/icoder-cloud/icoder-docs/edit/main/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'light',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'iCoDer',
      logo: {
        alt: 'iCoDer Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: '文档',
        },
        {
          href: 'https://github.com/icoder-cloud/icoder-docs',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: '文档',
          items: [
            {
              label: '快速开始',
              to: '/docs/intro',
            },
          ],
        },
        {
          title: '更多',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/icoder-cloud/icoder-docs',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} iCoDer. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
