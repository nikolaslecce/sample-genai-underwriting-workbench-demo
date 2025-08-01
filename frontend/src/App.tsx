import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, useNavigate, useParams } from 'react-router-dom'
import './styles/App.css'
import { JobPage } from './components/JobPage'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faShieldAlt,
  faFileAlt,
  faFileMedical,
  faList,
  faCalendarAlt,
  faCheckCircle,
  faHourglassHalf,
  faExclamationCircle,
  faSearch,
  faTimes,
} from '@fortawesome/free-solid-svg-icons'

function UploadPage() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate();

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    setError(null)

    if (!selectedFile) {
      return
    }

    if (!selectedFile.type.includes('pdf')) {
      setError('Please select a PDF file')
      return
    }

    setFile(selectedFile)
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file first')
      return
    }

    setUploading(true)
    setError(null)

    try {
      // Step 1: Get presigned URL from your backend
      const presignedUrlResponse = await fetch(`${import.meta.env.VITE_API_URL}/documents/upload`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filename: file.name,
          contentType: file.type, // Send file's content type
          insuranceType: 'life' // Send insurance type to backend
        }),
      })

      if (!presignedUrlResponse.ok) {
        if (presignedUrlResponse.status === 401) {
          setError("Unauthorized: API access denied for generating upload URL.");
        } else {
          const errorData = await presignedUrlResponse.json().catch(() => ({ error: 'Failed to get upload URL.' }));
          throw new Error(errorData.error || `Failed to get upload URL: ${presignedUrlResponse.statusText}`);
        }
        setUploading(false);
        return;
      }

      const { uploadUrl, jobId, s3Key: returnedS3Key } = await presignedUrlResponse.json() // Expect jobId and s3Key
      if (!uploadUrl || !jobId || !returnedS3Key) { // Check for jobId and returnedS3Key
        throw new Error('Invalid response from upload URL generation endpoint. Missing uploadUrl, jobId, or s3Key.');
      }

      // Step 2: Upload the file directly to S3 using the presigned URL
      const s3UploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
          'Content-Type': file.type, // Use the actual file type
        },
        body: file,
      })

      if (!s3UploadResponse.ok) {
        throw new Error(`S3 Upload Failed: ${s3UploadResponse.statusText}`)
      }

      // S3 upload successful, processing will be triggered by S3 event
      setUploading(false);
      setFile(null);
      // if (fileInputRef.current) { // Temporarily comment out if fileInputRef is causing issues
      //   fileInputRef.current.value = ""; // Reset file input
      // }
      // alert("File uploaded successfully. Processing will start automatically via S3 event.");

      // Navigate to the job-specific page
      if (jobId) {
        navigate(`/jobs/${jobId}`);
      } else {
        // This case should ideally not be hit if the API guarantees a jobId on success
        setError("File uploaded, but job tracking ID was not returned. Please check the jobs list.");
        // Optionally, navigate to a general jobs page or show a less disruptive message
        // navigate("/jobs");
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload and processing failed')
      setUploading(false)
    }
  }

  return (
    <div className="container">
      <div className="header">
        <h1>
          <span className="header-logo">
            <FontAwesomeIcon icon={faShieldAlt} />
          </span>
          GenAI Underwriting Workbench
        </h1>
        <div className="header-controls">
        <button
          type="button"
          onClick={() => navigate('/jobs')}
          className="nav-button"
        >
          <FontAwesomeIcon icon={faList} style={{ marginRight: '8px' }} />
          View All Jobs
        </button>
    </div>

      </div>
      <div className="upload-section">
        <h2>
          <FontAwesomeIcon icon={faFileMedical} style={{ marginRight: '10px', color: '#3b82f6' }} />
          Upload Document
        </h2>

        <div className="file-input-container">
          <input
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            multiple
            disabled={uploading}
            className="file-input"
          />
        </div>

        {file && (
          <div className="file-info">
            <p>Selected file: {file.name}</p>
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="upload-button"
            >
              {uploading ? 'Uploading...' : 'Analyze Document'}
            </button>
          </div>
        )}

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

// Wrapper to extract jobId from URL params
function JobPageWrapper() {
  const params = useParams<{ jobId: string }>()
  return <JobPage jobId={params.jobId!} />
}

// Add this new type definition
interface Job {
  jobId: string;
  originalFilename: string;
  uploadTimestamp: string;
  status: 'Complete' | 'In Progress' | 'Failed';
}

// Add the JobsList component
function JobsList() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const handleSearch = () => {
    setSearchQuery(searchInput.trim());
  };

  const handleClear = () => {
    setSearchInput('');
    setSearchQuery('');
  };

  const handleKeyDown = (e: any) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const filteredJobs = searchQuery
  ? jobs.filter(job =>
      job.originalFilename.toLowerCase().includes(searchQuery.toLowerCase())
    )
  : jobs;


  useEffect(() => {
    fetchJobs();
  }, []);

  const fetchJobs = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/jobs`, {
      });

      if (!response.ok) {
        if (response.status === 401) {
          setError("Unauthorized: API access denied.");
          setLoading(false);
          return;
        }
        throw new Error('Failed to fetch jobs');
      }

      const data = await response.json();
      setJobs(data.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (iso: string) => {
    const date = new Date(iso);
    if (isNaN(date.getTime())) return 'Invalid date';
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'Complete':
        return <FontAwesomeIcon icon={faCheckCircle} className="status-icon complete" />;
      case 'In Progress':
        return <FontAwesomeIcon icon={faHourglassHalf} className="status-icon in-progress" />;
      case 'Failed':
        return <FontAwesomeIcon icon={faExclamationCircle} className="status-icon failed" />;
      default:
        return null;
    }
  };

  return (
    <div className="container">
      <div className="header">
        <h1>
          <span className="header-logo">
            <FontAwesomeIcon icon={faShieldAlt} />
          </span>
          GenAI Underwriting Workbench
        </h1>
        <div className="header-controls">
          <button onClick={() => navigate('/')} className="nav-button">
            <FontAwesomeIcon icon={faFileMedical} /> Upload New
          </button>
        </div>
      </div>

      <div className="jobs-section">
        <h2>
          <FontAwesomeIcon icon={faList} style={{ marginRight: '10px' }} />
          Your Analysis Jobs
        </h2>

        {loading ? (
          <div className="loading">Loading jobs...</div>
        ) : error ? (
          <div className="error-message">
            {error}
            <button
              onClick={fetchJobs}
              className="refresh-button"
            >
              Try Again
            </button>
          </div>
        ) : jobs.length === 0 ? (
          <div className="no-jobs">
            <p>You haven't uploaded any documents yet.</p>
            <button
              onClick={() => navigate('/')}
              className="upload-button"
            >
              Upload Your First Document
            </button>
          </div>
        ) : (
          <>
            <div
              className="search-container"
              style={{ textAlign: 'center', margin: '20px 0' }}
            >
              <input
                type="text"
                placeholder="Search by filename"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                onKeyDown={handleKeyDown}
                style={{ padding: '8px', width: '300px' }}
              />
              <button
                onClick={handleSearch}
                style={{
                  padding: '8px 12px',
                  marginLeft: '8px',
                  background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                <FontAwesomeIcon icon={faSearch} style={{ marginRight: '5px' }} />
                Search
              </button>
              <button
                onClick={handleClear}
                style={{
                  padding: '8px 12px',
                  marginLeft: '8px',
                  background: 'linear-gradient(135deg, #e5e7eb 0%, #d1d5db 100%)',
                  color: '#333',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                <FontAwesomeIcon icon={faTimes} style={{ marginRight: '5px' }} />
                Clear
              </button>
            </div>
            <div className="jobs-list">
              {filteredJobs.map(job => (
                <div
                  key={job.jobId}
                  className="job-card"
                  onClick={() => navigate(`/jobs/${job.jobId}`)}
                >
                  <div className="job-icon">
                    <FontAwesomeIcon icon={faFileAlt} />
                  </div>
                  <div className="job-details">
                    <h3 className="job-filename">
                      {job.originalFilename}
                    </h3>
                    <div className="job-meta">
                      <div className="job-date">
                        <FontAwesomeIcon icon={faCalendarAlt} />
                        {formatDate(job.uploadTimestamp)}
                      </div>
                      <div
                        className={`job-status ${
                          job.status.toLowerCase().replace(' ', '-')
                        }`}
                      >
                        {getStatusIcon(job.status)}
                        {job.status}
                      </div>
                    </div>
                  </div>
                </div>
            ))}
          </div>
          </>

        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <>
        <Router>
            <Routes>
              <Route path="/" element={
                <UploadPage />
              } />
              <Route path="/jobs" element={
                <JobsList />
              } />
              <Route path="/jobs/:jobId" element={
                <JobPageWrapper />
              } />
            </Routes>
          </Router>
    </>

  )
}

export default App
