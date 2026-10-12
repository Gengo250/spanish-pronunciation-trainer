import { createHashRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import Home from "./routes/Home";
import Practice from "./routes/Practice";
import Progress from "./routes/Progress";

/**
 * Hash routing: the app is served as static files next to the API, with no
 * server-side rewrite rule, so hash routes keep deep links and the browser's
 * back button working without extra configuration.
 */
const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: "practice", element: <Practice /> },
      { path: "progress", element: <Progress /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
