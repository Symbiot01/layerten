PR_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 25, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      totalCount
      nodes {
        number
        title
        body
        state
        createdAt
        updatedAt
        mergedAt
        closedAt
        baseRefName
        headRefName
        additions
        deletions
        changedFiles
        author { login }
        mergeCommit { oid }
        labels(first: 20) {
          nodes { name }
        }
        assignees(first: 10) {
          nodes { login }
        }
        reviews(first: 50) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            state
            body
            createdAt
            author { login }
            comments(first: 50) {
              pageInfo { hasNextPage endCursor }
              nodes {
                body
                path
                line
                createdAt
                author { login }
              }
            }
          }
        }
        comments(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            body
            createdAt
            author { login }
          }
        }
        timelineItems(first: 100, itemTypes: [
          CLOSED_EVENT
          MERGED_EVENT
          LABELED_EVENT
          UNLABELED_EVENT
          ASSIGNED_EVENT
          CROSS_REFERENCED_EVENT
          RENAMED_TITLE_EVENT
        ]) {
          nodes {
            __typename
            ... on ClosedEvent {
              createdAt
              actor { login }
            }
            ... on MergedEvent {
              createdAt
              actor { login }
              commit { oid }
            }
            ... on LabeledEvent {
              createdAt
              label { name }
              actor { login }
            }
            ... on UnlabeledEvent {
              createdAt
              label { name }
              actor { login }
            }
            ... on AssignedEvent {
              createdAt
              assignee { ... on User { login } }
              actor { login }
            }
            ... on CrossReferencedEvent {
              createdAt
              actor { login }
              source {
                ... on Issue { number title }
                ... on PullRequest { number title }
              }
            }
            ... on RenamedTitleEvent {
              createdAt
              previousTitle
              currentTitle
              actor { login }
            }
          }
        }
      }
    }
  }
}
"""

PR_REVIEWS_SUBPAGE_QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviews(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          state
          body
          createdAt
          author { login }
          comments(first: 50) {
            pageInfo { hasNextPage endCursor }
            nodes {
              body
              path
              line
              createdAt
              author { login }
            }
          }
        }
      }
    }
  }
}
"""

PR_COMMENTS_SUBPAGE_QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          author { login }
        }
      }
    }
  }
}
"""

ISSUE_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issues(first: 25, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      totalCount
      nodes {
        number
        title
        body
        state
        createdAt
        updatedAt
        closedAt
        author { login }
        labels(first: 20) {
          nodes { name }
        }
        assignees(first: 10) {
          nodes { login }
        }
        comments(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            body
            createdAt
            author { login }
          }
        }
        timelineItems(first: 100, itemTypes: [
          CLOSED_EVENT
          LABELED_EVENT
          UNLABELED_EVENT
          ASSIGNED_EVENT
          CROSS_REFERENCED_EVENT
          RENAMED_TITLE_EVENT
        ]) {
          nodes {
            __typename
            ... on ClosedEvent {
              createdAt
              actor { login }
            }
            ... on LabeledEvent {
              createdAt
              label { name }
              actor { login }
            }
            ... on UnlabeledEvent {
              createdAt
              label { name }
              actor { login }
            }
            ... on AssignedEvent {
              createdAt
              assignee { ... on User { login } }
              actor { login }
            }
            ... on CrossReferencedEvent {
              createdAt
              actor { login }
              source {
                ... on Issue { number title }
                ... on PullRequest { number title }
              }
            }
            ... on RenamedTitleEvent {
              createdAt
              previousTitle
              currentTitle
              actor { login }
            }
          }
        }
      }
    }
  }
}
"""

ISSUE_COMMENTS_SUBPAGE_QUERY = """
query($owner: String!, $repo: String!, $issueNumber: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issue(number: $issueNumber) {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          author { login }
        }
      }
    }
  }
}
"""

DISCUSSION_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: 25, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      totalCount
      nodes {
        number
        title
        body
        createdAt
        updatedAt
        author { login }
        category { name }
        labels(first: 20) {
          nodes { name }
        }
        comments(first: 50) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            body
            createdAt
            author { login }
            replies(first: 20) {
              pageInfo { hasNextPage endCursor }
              nodes {
                id
                body
                createdAt
                author { login }
              }
            }
          }
        }
      }
    }
  }
}
"""

DISCUSSION_COMMENTS_SUBPAGE_QUERY = """
query($owner: String!, $repo: String!, $discNumber: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    discussion(number: $discNumber) {
      comments(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          author { login }
          replies(first: 20) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              body
              createdAt
              author { login }
            }
          }
        }
      }
    }
  }
}
"""
