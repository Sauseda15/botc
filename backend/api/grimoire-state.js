const express = require('express');
const router = express.Router();

// Mock data from the Discord bot's backend state
const grimoirePlayers = [
  {
    id: 1,
    name: 'Alice',
    role: 'Chef',
    alignment: 'Good',
    token: '🔪',
    isAlive: true,
  },
  {
    id: 2,
    name: 'Bob',
    role: 'Minion',
    alignment: 'Evil',
    token: '🕷️',
    isAlive: true,
  },
  {
    id: 3,
    name: 'Charlie',
    role: 'Empath',
    alignment: 'Good',
    token: '🧠',
    isAlive: true,
  },
  {
    id: 4,
    name: 'Dana',
    role: 'Demon',
    alignment: 'Evil',
    token: '👹',
    isAlive: false,
  },
  {
    id: 5,
    name: 'Eli',
    role: 'Townsfolk',
    alignment: 'Good',
    token: '👒',
    isAlive: true,
  },
];

// GET /api/grimoire-state
router.get('/', (req, res) => {
  res.json({ players: grimoirePlayers });
});

module.exports = router;
