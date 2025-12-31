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
    'Third Place': 'Third Place Play-off',
    'Third Place Play': 'Third Place Play-off',
    'Third Place Playoff': 'Third Place Play-off',
    '3rd Place Play-off': 'Third Place Play-off',
    'Second Place': 'Final'
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
