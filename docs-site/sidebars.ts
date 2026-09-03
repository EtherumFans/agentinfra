import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    {
      type: 'category',
      label: 'Getting Started',
      items: ['intro', 'quickstart'],
    },

    // Scaffold placeholders — content migration tracked in Sprint 2.
    // Each entry below is a docs/*.md file to be migrated from /docs/.
    // Sprint 1 only ships the scaffold; do not add content yet.
    {
      type: 'category',
      label: '开发者指南 (Sprint 2 占位)',
      items: [
        'placeholders/sdk',
        'placeholders/api-clients',
        'placeholders/quickstart-detail',
      ],
    },
  ],
};

export default sidebars;
