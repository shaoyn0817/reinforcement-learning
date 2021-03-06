import gym
import numpy as np
import tensorflow as tf
from memory import *


initializer_helper = {
    'kernel_initializer': tf.random_normal_initializer(0., 0.3),
    'bias_initializer': tf.constant_initializer(0.1)
}


class DQN(object):
    def __init__(self, sess, s_dim, a_dim, batch_size, gamma, lr, epsilon, replace_target_iter):
        self.sess = sess
        self.s_dim = s_dim  # 状态维度
        self.a_dim = a_dim  # one hot行为维度
        self.gamma = gamma
        self.lr = lr  # learning rate
        self.epsilon = epsilon  # epsilon-greedy
        self.replace_target_iter = replace_target_iter  # 经历C步后更新target参数

        self.memory = Memory(batch_size, 16384, 0.9)
        self._learn_step_counter = 0
        self._generate_model()

    def choose_action(self, s):
        if np.random.rand() < self.epsilon:
            return np.random.randint(self.a_dim)
        else:
            q_eval_z = self.sess.run(self.q_eval_z, feed_dict={
                self.s: s[np.newaxis, :]
            })
            return q_eval_z.squeeze().argmax()

    def _generate_model(self):
        self.s = tf.placeholder(tf.float32, shape=(None, self.s_dim), name='s')
        self.a = tf.placeholder(tf.float32, shape=(None, self.a_dim), name='a')
        self.r = tf.placeholder(tf.float32, shape=(None, 1), name='r')
        self.s_ = tf.placeholder(tf.float32, shape=(None, self.s_dim), name='s_')
        self.done = tf.placeholder(tf.float32, shape=(None, 1), name='done')

        self.importance_ratio = tf.placeholder(tf.float32, shape=(None, 1), name='importance_ratio')

        self.q_eval_z = self._build_net(self.s, 'eval_net', True)
        self.q_target_z = self._build_net(self.s_, 'target_net', False)

        # argmax(Q)
        max_a = tf.argmax(self.q_eval_z, axis=1)
        one_hot_max_a = tf.one_hot(max_a, self.a_dim)

        # y = R + gamma * Q_(S, argmax(Q))
        q_target = self.r + self.gamma \
            * tf.reduce_sum(one_hot_max_a * self.q_target_z, axis=1, keepdims=True) * (1 - self.done)
        q_target = tf.stop_gradient(q_target)

        q_eval = tf.reduce_sum(self.a * self.q_eval_z, axis=1, keepdims=True)

        self.td_error = tf.abs(q_target - q_eval)

        self.loss = tf.reduce_mean(tf.squared_difference(q_target, q_eval)) * self.importance_ratio
        self.optimizer = tf.train.AdamOptimizer(self.lr).minimize(self.loss)

        param_target = tf.global_variables(scope='target_net')
        param_eval = tf.global_variables(scope='eval_net')

        # 将eval网络参数复制给target网络
        self.target_replace_ops = [tf.assign(t, e) for t, e in zip(param_target, param_eval)]

    def _build_net(self, s, scope, trainable):
        with tf.variable_scope(scope):
            l = tf.layers.dense(s, 20, activation=tf.nn.relu, trainable=trainable, ** initializer_helper)
            q_z = tf.layers.dense(l, self.a_dim, trainable=trainable, **initializer_helper)

        return q_z

    def store_transition_and_learn(self, s, a, r, s_, done):
        if self._learn_step_counter % self.replace_target_iter == 0:
            self.sess.run(self.target_replace_ops)

        # 将行为转换为one hot形式
        one_hot_action = np.zeros(self.a_dim)
        one_hot_action[a] = 1

        self.memory.store_transition(s, one_hot_action, [r], s_, [done])
        self._learn()
        self._learn_step_counter += 1

    def _learn(self):
        points, (s, a, r, s_, done), importance_ratio = self.memory.get_mini_batches()

        td_error, _ = self.sess.run([self.td_error, self.optimizer], feed_dict={
            self.s: s,
            self.a: a,
            self.r: r,
            self.s_: s_,
            self.done: done,
            self.importance_ratio: np.array([importance_ratio]).T
        })

        self.memory.update(points, td_error.squeeze(axis=1))
