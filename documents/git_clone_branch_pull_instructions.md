This doc explains
1. how to clone the repo to your workspace,
2. how to interact with it via branches,
3. how forking Le Wagon challenge repos may be useful.

- - -

# CLONE REPO

1. Check you have GitHub installed `git -- version`
2. Login, (if you are not already) choose https and browser `gh auth login`
3. Check the repo is in your list (make sure you accepted the email invite) `gh repo list`
4. Clone the repo `gh repo clone [insert your username]/Berlin_traffic_data`
5. Go into the repo `cd Berlin_traffic_data/`followed by `code .` You should see the files.


# BRANCHING

**Nobody works on main or dev. -> Never push to main or dev.**
**Everybody works on their own branch to avoid merge conflicts**
* If you are collaborating on the same work package (i.e. the Dashboard) create two different branches (i.e. dashboard_sliders and dashboard_graphs) and keep the tasks seperate.
* If you want to collaborate on the same lines of code, do it via screenshare.

## Branching structure
```
main          ← final code only
└──
    ├── ingest        ← one branch
    ├── cleaning      ← another branch
    ├── dashboard     ← another branch
    └── etc.          ← any new work package
```

## How this works in practice

1. whenever you start on a new work package **check out the latest code** from the `main`branch:
     `git checkout dev`
     `git pull`

2. if you start a new work package, **create your own new branch**. Give it a name that makes sense:
    `git checkout -b dashboard_sliders`

3. work on it and at end of the day **save your work** to your branch as you have been:
    `git add .`
    `git commit -m "fixed timeframe selection function bug"` ← meaningful messages for reviewer and team
    `git push origin dashboard_sliders` ← Never push to main or dev

4. To **continue working** on your own branch after a break, check it out again:
    `git checkout dashboard_sliders`

5. It's good practice to **regularily check and sync** work from collaborators (i.e. every 24h):
    `git merge origin main`          ← grab anything collaborators merged yesterday

6. Once you are done with your work package **submit your work** via a pull request:
    `gh pr create`  ← follow prompts, add title (summary of work), body (more detail), base branch (use `main`)

    or use full command:

    `gh pr create --base main --title "added data cleaning logic" --body "implemented clean_data function in ingest_clean.py"`

7. Supervisor will get notification on GitHub, they approve, leave comments or request changes.

8. You will get notified of comments or change requests. Repeat steps 4. then 5. then 3. to **address the comments**. Your pull request will be automatically updated. You do not need to open or close a pull request. You can check teh status and commenst on your pull requests:
   `gh pr view --comments`

9.  Once the code is final, the supervisor will approve it (easiest via GitHub UI). You will see that your branch shows as merged. Quickly **verify your code is there**:
    `git checkout main`
    `git pull origin main`

10. Once the work package is completed, **delete your branch** to keep the repo tidy:
    `git branch -d dashboard_sliders`
    `git push origin --delete dashboard_sliders`
