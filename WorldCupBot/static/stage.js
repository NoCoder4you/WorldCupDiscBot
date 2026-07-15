(() => {
  'use strict';

  const STAGE_ORDER = [
    'Eliminated',
    'Group Stage',
    'Round of 32',
    'Round of 16',
    'Quarter-finals',
    'Semi-finals',
    'Third Place Play-off',
    'Final',
    '2nd Place',
    '3rd Place',
    'Winner'
  ];

  const STAGE_ALIASES = {
    Group: 'Group Stage',
    R32: 'Round of 32',
    R16: 'Round of 16',
    QF: 'Quarter-finals',
    SF: 'Semi-finals',
    F: 'Final',
    'Quarter Final': 'Quarter-finals',
    'Quarter Finals': 'Quarter-finals',
    'Semi Final': 'Semi-finals',
    'Semi Finals': 'Semi-finals',
    // Outcome labels are distinct from match-round labels so admins can
    // mark runners-up/third-place finishers from the Ownership page.
    'Third Place': '3rd Place',
    'Third Place Play': 'Third Place Play-off',
    'Third Place Playoff': 'Third Place Play-off',
    '3rd Place Play-off': 'Third Place Play-off',
    'Third Place Match': 'Third Place Play-off',
    'Second Place': '2nd Place',
    'Runner-up': '2nd Place',
    'Runner Up': '2nd Place'
  };

  const STAGE_PROGRESS = {
    Eliminated: 0,
    'Group Stage': 15,
    'Round of 32': 25,
    'Round of 16': 35,
    'Quarter-finals': 55,
    'Semi-finals': 70,
    'Third Place Play-off': 80,
    Final: 90,
    '2nd Place': 95,
    '3rd Place': 85,
    Winner: 100
  };

  function normalizeStage(label) {
    const s = String(label || '').trim();
    return STAGE_ALIASES[s] || s;
  }

  window.WorldCupStages = {
    STAGE_ORDER,
    STAGE_ALIASES,
    STAGE_PROGRESS,
    normalizeStage
  };
})();
