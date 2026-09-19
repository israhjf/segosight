import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * Who is reviewing.
 *
 * The API refuses an anonymous decision, and rightly so: approving a
 * prose-derived claim promotes it into operational record, and that has to be
 * attributable. In a deployment this comes from SSO; here it is a named
 * profile so the audit trail is still real.
 */
const ReviewerContext = createContext<{
  reviewer: string;
  setReviewer: (name: string) => void;
}>({ reviewer: "Dana Whitlock", setReviewer: () => {} });

export function ReviewerProvider({ children }: { children: ReactNode }) {
  const [reviewer, setReviewer] = useState("Dana Whitlock");
  const value = useMemo(() => ({ reviewer, setReviewer }), [reviewer]);
  return <ReviewerContext.Provider value={value}>{children}</ReviewerContext.Provider>;
}

export const useReviewer = () => useContext(ReviewerContext);
