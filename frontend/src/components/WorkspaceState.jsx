import React, { createContext, useContext, useState } from 'react';

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({ children }) {
  const [values, setValues] = useState({});
  return <WorkspaceContext.Provider value={{ values, setValues }}>{children}</WorkspaceContext.Provider>;
}

// Keep work while switching pages. A full browser reload starts a new session.
export function useWorkspaceState(key, initialValue) {
  const { values, setValues } = useContext(WorkspaceContext);
  const value = Object.hasOwn(values, key) ? values[key] : initialValue;
  function update(next) {
    setValues(previous => {
      const current = Object.hasOwn(previous, key) ? previous[key] : initialValue;
      return { ...previous, [key]: typeof next === 'function' ? next(current) : next };
    });
  }
  return [value, update];
}
