import '@testing-library/jest-dom';

// Mock IndexedDB
const indexedDB = {
  open: jest.fn(() => ({
    result: {
      objectStoreNames: { contains: jest.fn(() => true) },
      transaction: jest.fn(() => ({
        objectStore: jest.fn(() => ({
          put: jest.fn(),
          get: jest.fn(),
          getAll: jest.fn(),
          delete: jest.fn(),
        })),
      })),
      createObjectStore: jest.fn(),
    },
    onsuccess: null,
    onerror: null,
    onupgradeneeded: null,
  })),
};

global.indexedDB = indexedDB as any;

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

global.localStorage = localStorageMock as any;
