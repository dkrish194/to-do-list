pipeline{
    agent{
        node{
            label   '186.3'
        }
    }
    stages{

        stage("READ FRONTEND VERSION"){
            steps{
                script{
                    dir('frontend'){
                        def fe_app_version = sh (script: 'cut -d "=" -f 2  setup-frontend.cfg',returnStdout: true).trim()
                        echo "Extraced frontend appverion value: ${fe_app_version}"
                        env.FE_APP_VERSION=fe_app_version
                    }
                    
                }
            }
        }
        stage("READ BACKEND VERSION"){
            steps{
                script{
                    def fe_app_version = sh (script: 'cut -d "=" -f 2  backend/setup-backend.cfg',returnStdout: true).trim()
                    echo "Extraced backend appverion value: ${be_app_version}"
                    env.BE_APP_VERSION=be_app_version
                }
            }
        }
        stage("BUILD FRONTEND IMAGE"){
            steps{
                echo "Building frontend Image"
                sh "docker build -t dkrish194/todo-frontend:${env.FE_APP_VERSION} frontend/Dockerfile"
            }
        }
        stage("BUILD BACKEND IMAGE"){
            steps{
                echo "Buildig Backend Image"
                sh "docker build -t dkrish194/todo-backend:${env.BE_APP_VERSION} backend/Dockerfile"
            }
        }

        stage("DOCKER LOGIN"){
            steps{
                echo "Docker login"
                withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'
                                }
            }
        }

        stage("DOCKER PUSH FRONTEND"){
            steps{
                 echo "Docker Push Frontend"
            withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'docker push dkrish194/todo-frontend:${env.FE_APP_VERSION}'
                                }
            }
           
        }
        stage("DOCKER PUSH BACKEND"){
            steps{
                 echo "Docker Push Backend"
                 withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh "docker push dkrish194/todo-backend:${env.BE_APP_VERSION}"
                                }
            }
           
        }
        
      
    }
}