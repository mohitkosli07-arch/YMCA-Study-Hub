# YMCA Study Hub V4
## New contribution system
Required public fields: Name, Roll No., Branch, Semester, Phone No., What to contribute.
No email and no public file upload.

Students submit details -> staff sees them in private dashboard -> staff contacts student -> student sends PDF/material separately -> staff compares submissions -> staff publishes the selected resource.

## Staff-only dashboard
`/staff` requires STAFF_NAME + STAFF_PASSWORD.
For local PowerShell:
`$env:STAFF_NAME="Your Name"`
`$env:STAFF_PASSWORD="Your Strong Password"`
`$env:SECRET_KEY="random-long-secret"`
`python app.py`

For Render, add these as Environment Variables.

## Leaderboard
Only published contributions count. It shows contributor name, branch, semester, and number of published contributions.

## V5 changes
- Staff password has NO usable default. Set `STAFF_NAME`, `STAFF_PASSWORD`, and `SECRET_KEY` in local environment or Render.
- `/staff` is private and protected by login/session.
- Public leaderboard has a **View Contributions** button for each student.
- Each contribution detail shows the published title, branch, semester, subject, category, contributor, and publication timestamp.
- Leaderboard counts published contribution records only.

## V6: Staff-only content control
- Public students can only view website content and submit contribution details.
- Only authenticated staff can access `/staff`.
- Staff dashboard has Add/Edit/Delete resource controls.
- Staff has an explicit Logout action.
- Public `/contribution` page offers exactly two choices: Want to Contribute? and Contribution Leaderboard.

## V7: Explicit Staff Login Flow
Public Staff navigation is now:
`Staff -> /staff -> Staff Login -> Name + Password -> /staff/dashboard`

The contribution dashboard and resource management pages are protected by the authenticated staff session.
Logout clears the session and returns to the public home page.

## V8: Clean access flow
Staff: `Staff -> Login (name + password) -> Dashboard -> Resources -> Logout`

Starter local credentials:
- Name: `Mohit`
- Password: `YMCA@Admin2026`

For production, set `STAFF_NAME`, `STAFF_PASSWORD`, and `SECRET_KEY` as private environment variables.

Contribution: `Contribution -> Want to Contribute?` OR `Contribution -> Contribution Leaderboard`.

The old `/leaderboard` URL is disabled. The staff dashboard contains no leaderboard/contribution links.

## V9: Public Staff button
The public navigation now visibly contains `Staff`.
Clicking it always goes to `/staff`, which redirects logged-out users to the Staff Login page.
The public Staff button never exposes the dashboard directly.


### Resource visibility fix
Published resources are now normalized to the same canonical branch, semester, and subject values used by the public subject pages. This fixes cases where a resource showed as published in Staff but appeared as "No resource added yet" on the subject page. Existing database rows are also normalized automatically at startup.


## V10: Direct file upload
- Staff can upload PDF/DOC/DOCX/PPT/PPTX/TXT files directly from Add Resource and Publish.
- Uploaded files are stored in `static/resources/uploads/` with unique filenames.
- Maximum upload size is 25 MB.
- The database stores the generated relative path automatically.
- On Render, local uploaded files are not permanent across redeploys/restarts unless persistent storage is configured. For production, use Render persistent disk or object storage.
